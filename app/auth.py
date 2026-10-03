"""Пользователи, сессии и login-токены. Общий слой для сайта и Telegram-бота.

Здесь только работа с базой — ни FastAPI, ни aiogram импортировать сюда нельзя:
модуль подключают оба процесса. Функции синхронные; бот вызывает их через
asyncio.to_thread, чтобы не блокировать свой цикл.
"""
import logging
import secrets
import time

from app import db
from app.config import LOGIN_TOKEN_TTL, SESSION_TTL, TELEGRAM_BOT_USERNAME

log = logging.getLogger("tajscore.auth")

FAV_TYPES = ("team", "league", "match")


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ пользователи
def get_user(user_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    return dict(row) if row else None


def get_user_by_tg(telegram_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    return dict(row) if row else None


def upsert_user(telegram_id: int, display_name: str, username: str | None,
                phone: str | None) -> tuple[dict, bool]:
    """Заводит или обновляет пользователя. Возвращает (пользователь, новый ли он).

    Имя и username берём из профиля Telegram при каждом входе — человек мог
    их сменить. Телефон не затираем пустым значением: контакт присылают один раз.
    """
    now = _now()
    existing = get_user_by_tg(telegram_id)
    if existing:
        db.execute(
            """UPDATE users SET display_name=?, username=?,
                   phone=COALESCE(?, phone), last_login=?, is_blocked=0
               WHERE telegram_id=?""",
            (display_name, username, phone, now, telegram_id))
        return get_user_by_tg(telegram_id), False

    db.execute(
        """INSERT INTO users (telegram_id, display_name, username, phone,
                              notifications_enabled, created_at, last_login)
           VALUES (?,?,?,?,1,?,?)""",
        (telegram_id, display_name, username, phone, now, now))
    return get_user_by_tg(telegram_id), True


def touch_login(user_id: int) -> None:
    db.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), user_id))


def set_notifications(user_id: int, enabled: bool) -> None:
    db.execute("UPDATE users SET notifications_enabled=? WHERE id=?",
               (1 if enabled else 0, user_id))


def mark_blocked(telegram_id: int, blocked: bool = True) -> None:
    """Пользователь заблокировал бота — исключаем его из рассылок."""
    db.execute("UPDATE users SET is_blocked=? WHERE telegram_id=?",
               (1 if blocked else 0, telegram_id))


def public_user(user: dict) -> dict:
    """То, что можно отдавать в браузер. Телефона здесь нет и быть не должно."""
    return {
        "id": user["id"],
        "name": user["display_name"],
        "username": user["username"],
        "notifications": bool(user["notifications_enabled"]),
    }


# ------------------------------------------------------------------ сессии
def create_session() -> str:
    """Пустая (гостевая) сессия. Нужна, чтобы было к чему привязать login-токен."""
    sid = secrets.token_urlsafe(32)
    now = _now()
    db.execute(
        "INSERT INTO sessions (id, user_id, created_at, last_seen, expires_at) VALUES (?,NULL,?,?,?)",
        (sid, now, now, now + SESSION_TTL))
    return sid


def get_session(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    row = db.query_one("SELECT * FROM sessions WHERE id=? AND expires_at>?",
                       (session_id, _now()))
    return dict(row) if row else None


def session_user(session_id: str | None) -> dict | None:
    """Пользователь текущей сессии либо None. Заодно продлевает сессию."""
    if not session_id:
        return None
    row = db.query_one(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.id=? AND s.expires_at>?""", (session_id, _now()))
    if not row:
        return None
    now = _now()
    db.execute("UPDATE sessions SET last_seen=?, expires_at=? WHERE id=?",
               (now, now + SESSION_TTL, session_id))
    return dict(row)


def bind_session(session_id: str, user_id: int) -> None:
    now = _now()
    db.execute("UPDATE sessions SET user_id=?, last_seen=?, expires_at=? WHERE id=?",
               (user_id, now, now + SESSION_TTL, session_id))


def drop_session(session_id: str) -> None:
    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))


# ------------------------------------------------------------------ login-токены
def create_login_token(session_id: str, device: str | None = None) -> dict:
    """Одноразовый токен для deep-link. Старые токены этой сессии гасим —
    иначе две открытые вкладки дадут два живых входа.

    device — краткое имя браузера («Windows / Chrome»). Бот показывает его в
    запросе «Это вы входите?»: если ссылку переслал мошенник, человек увидит
    чужое устройство и нажмёт «Это не я»."""
    now = _now()
    db.execute("DELETE FROM login_tokens WHERE session_id=? OR expires_at<?",
               (session_id, now))
    token = secrets.token_urlsafe(24)   # 32 символа — влезает в лимит deep-link (64)
    db.execute(
        """INSERT INTO login_tokens (token, session_id, created_at, expires_at, device)
           VALUES (?,?,?,?,?)""", (token, session_id, now, now + LOGIN_TOKEN_TTL, device))
    return {
        "token": token,
        "url": f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={token}",
        "expires_in": LOGIN_TOKEN_TTL,
    }


def get_login_token(token: str) -> dict | None:
    row = db.query_one("SELECT * FROM login_tokens WHERE token=?", (token,))
    return dict(row) if row else None


def confirm_login_token(token: str, telegram_id: int) -> str:
    """Вызывает бот после получения контакта.

    Возвращает 'ok' | 'unknown' | 'expired' | 'used'. Проверки идут именно здесь,
    чтобы у бота не было своей копии правил.
    """
    row = get_login_token(token)
    if not row:
        return "unknown"
    if row["rejected"]:
        return "rejected"
    if row["used"] or row["confirmed"]:
        return "used"
    if row["expires_at"] < _now():
        return "expired"
    # Условие в UPDATE — защита от гонки двух нажатий: подтвердит только первое
    cur = db.execute(
        "UPDATE login_tokens SET telegram_id=?, confirmed=1 WHERE token=? AND confirmed=0 AND rejected=0",
        (telegram_id, token))
    return "ok" if cur and cur.rowcount else "used"


def token_status(token: str) -> str:
    """Можно ли ещё подтвердить вход по токену: ok | unknown | expired | used | rejected."""
    row = get_login_token(token)
    if not row:
        return "unknown"
    if row["rejected"]:
        return "rejected"
    if row["used"] or row["confirmed"]:
        return "used"
    if row["expires_at"] < _now():
        return "expired"
    return "ok"


def reject_login_token(token: str, telegram_id: int) -> bool:
    """«Это не я»: токен гасится, вкладка, начавшая вход, получит отказ."""
    cur = db.execute(
        "UPDATE login_tokens SET rejected=1, telegram_id=? WHERE token=? AND confirmed=0",
        (telegram_id, token))
    if cur and cur.rowcount:
        log.warning("вход отклонён пользователем telegram_id=%s", telegram_id)
        return True
    return False


def claim_login_token(token: str, session_id: str) -> dict | None:
    """Сайт забирает подтверждённый токен: помечает использованным и привязывает
    пользователя к сессии. Токен обязан принадлежать именно этой сессии."""
    row = get_login_token(token)
    if not row or row["session_id"] != session_id:
        return None
    if row["used"] or not row["confirmed"] or row["expires_at"] < _now():
        return None
    db.execute("UPDATE login_tokens SET used=1 WHERE token=?", (token,))
    user = get_user_by_tg(row["telegram_id"])
    if not user:
        return None
    bind_session(session_id, user["id"])
    touch_login(user["id"])
    return user


def cleanup() -> None:
    """Протухшие токены и сессии. Дёргается при старте приложения."""
    now = _now()
    db.execute("DELETE FROM login_tokens WHERE expires_at < ?", (now - 3600,))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))


# ------------------------------------------------------------------ избранное
def list_favorites(user_id: int) -> dict[str, list[int]]:
    rows = db.query("SELECT type, item_id FROM favorites WHERE user_id=? ORDER BY created_at",
                    (user_id,))
    out: dict[str, list[int]] = {t: [] for t in FAV_TYPES}
    for r in rows:
        out.setdefault(r["type"], []).append(r["item_id"])
    return out


def toggle_favorite(user_id: int, fav_type: str, item_id: int) -> bool:
    """Возвращает новое состояние: True — добавлено, False — убрано."""
    if fav_type not in FAV_TYPES:
        raise ValueError(f"неизвестный тип избранного: {fav_type}")
    cur = db.execute("DELETE FROM favorites WHERE user_id=? AND type=? AND item_id=?",
                     (user_id, fav_type, item_id))
    if cur and cur.rowcount:
        return False
    db.execute("INSERT INTO favorites (user_id, type, item_id, created_at) VALUES (?,?,?,?)",
               (user_id, fav_type, item_id, _now()))
    return True


def merge_favorites(user_id: int, items: list[dict]) -> None:
    """Переносит избранное, накопленное гостем в localStorage, при первом входе."""
    now = _now()
    rows = []
    for i in items:
        # тело запроса приходит из браузера — проверяем, а не доверяем
        if not isinstance(i, dict) or i.get("type") not in FAV_TYPES:
            continue
        try:
            rows.append((user_id, i["type"], int(i["id"]), now))
        except (KeyError, TypeError, ValueError):
            continue
    if rows:
        db.executemany(
            "INSERT OR IGNORE INTO favorites (user_id, type, item_id, created_at) VALUES (?,?,?,?)",
            rows)
