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
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")   # ; — чтобы Excel открыл без «Импорта данных»
    w.writerow(["telegram_id", "имя", "username", "phone",
                "дата регистрации", "уведомления", "последний вход"])
    for r in rows:
        w.writerow([
            r["telegram_id"],
            r["display_name"],
            f"@{r['username']}" if r["username"] else "",
            r["phone"] or "",
            fmt_ts(r["created_at"]),
            "вкл" if r["notifications_enabled"] else "выкл",
            fmt_ts(r["last_login"]),
        ])
    # BOM — иначе Excel под Windows покажет кириллицу кракозябрами
    return buf.getvalue().encode("utf-8-sig")


async def csv_bytes() -> bytes:
    return await _run(_csv_bytes)


def fmt_ts(ts) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), TZ).strftime("%d.%m.%Y %H:%M")
