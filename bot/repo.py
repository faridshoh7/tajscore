"""Доступ к базе из бота.

app.auth и app.db синхронные (sqlite3), поэтому каждый вызов уводим в поток —
иначе на длинной выборке (CSV, рассылка) встанет весь цикл бота.
"""
import asyncio
import csv
import io
import time
from datetime import datetime, timedelta, timezone

from app import auth, db

TZ = timezone(timedelta(hours=5))   # Asia/Dushanbe, по нему считаем «сегодня»


async def _run(fn, *args):
    return await asyncio.to_thread(fn, *args)


# ------------------------------------------------------------------ вход
async def register(telegram_id: int, display_name: str, username: str | None,
                   phone: str | None) -> tuple[dict, bool]:
    return await _run(auth.upsert_user, telegram_id, display_name, username, phone)


async def confirm_token(token: str, telegram_id: int) -> str:
    return await _run(auth.confirm_login_token, token, telegram_id)


async def user_by_tg(telegram_id: int) -> dict | None:
    return await _run(auth.get_user_by_tg, telegram_id)


async def mark_blocked(telegram_id: int, blocked: bool = True) -> None:
    await _run(auth.mark_blocked, telegram_id, blocked)


# ------------------------------------------------------------------ админка
def _stats() -> dict:
    now = int(time.time())
    midnight = int(datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    week = now - 7 * 86400
    one = lambda sql, p=(): db.query_one(sql, p)["n"]
    return {
        "total": one("SELECT COUNT(*) n FROM users"),
        "today": one("SELECT COUNT(*) n FROM users WHERE created_at>=?", (midnight,)),
        "week": one("SELECT COUNT(*) n FROM users WHERE created_at>=?", (week,)),
        "notify": one("SELECT COUNT(*) n FROM users WHERE notifications_enabled=1 AND is_blocked=0"),
        "active": one("SELECT COUNT(*) n FROM users WHERE last_login>=?", (week,)),
        "blocked": one("SELECT COUNT(*) n FROM users WHERE is_blocked=1"),
        "favorites": one("SELECT COUNT(*) n FROM favorites"),
    }


async def stats() -> dict:
    return await _run(_stats)


def _recipients(only_notify: bool) -> list[int]:
    """Кому уходит рассылка. Заблокировавших бота пропускаем всегда."""
    sql = "SELECT telegram_id FROM users WHERE is_blocked=0"
    if only_notify:
        sql += " AND notifications_enabled=1"
    return [r["telegram_id"] for r in db.query(sql)]


async def recipients(only_notify: bool) -> list[int]:
    return await _run(_recipients, only_notify)


def _find(term: str) -> list[dict]:
    term = term.strip().lstrip("@")
    if not term:
        return []
    if term.isdigit():
        rows = db.query("SELECT * FROM users WHERE telegram_id=?", (int(term),))
        if rows:
            return [dict(r) for r in rows]
    rows = db.query(
        "SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ? LIMIT 10",
        (f"%{term}%", f"%{term}%"))
    return [dict(r) for r in rows]


async def find_users(term: str) -> list[dict]:
    return await _run(_find, term)


def _csv_bytes() -> bytes:
    rows = db.query("SELECT * FROM users ORDER BY created_at")
    lines: list[str] = []
    data = []
    for r in rows:
        data.append({
            "name": r["display_name"] or "—",
            "user": f"@{r['username']}" if r["username"] else "—",
            "phone": r["phone"] or "—",
            "reg": fmt_ts(r["created_at"]) or "—",
            "notif": "вкл" if r["notifications_enabled"] else "выкл",
            "last": fmt_ts(r["last_login"]) or "—",
        })
    if not data:
        return "Пользователей нет.".encode("utf-8-sig")
    w_name = max(len(d["name"]) for d in data)
    w_user = max(len(d["user"]) for d in data)
    w_phone = max(len(d["phone"]) for d in data)
    w_reg = max(len(d["reg"]) for d in data)
    w_name = max(w_name, 6)
    w_user = max(w_user, 8)
    gap = "    "
    header = (
        f"{'Имя':<{w_name}}{gap}"
        f"{'Юзернейм':<{w_user}}{gap}"
        f"{'Телефон':<{w_phone}}{gap}"
        f"{'Регистрация':<{w_reg}}{gap}"
        f"{'Увед.':<5}{gap}"
        f"Последний вход"
    )
    lines.append(header)
    lines.append("─" * len(header))
    for d in data:
        lines.append(
            f"{d['name']:<{w_name}}{gap}"
            f"{d['user']:<{w_user}}{gap}"
            f"{d['phone']:<{w_phone}}{gap}"
            f"{d['reg']:<{w_reg}}{gap}"
            f"{d['notif']:<5}{gap}"
            f"{d['last']}"
        )
    lines.append("─" * len(header))
    lines.append(f"Всего: {len(data)}")
    return "\r\n".join(lines).encode("utf-8-sig")


async def csv_bytes() -> bytes:
    return await _run(_csv_bytes)


def fmt_ts(ts) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), TZ).strftime("%d.%m.%Y %H:%M")
