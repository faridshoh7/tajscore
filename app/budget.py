"""Учёт дневного расхода запросов к API-Football.

Бесплатный тариф = 100 запросов в сутки, счётчик у api-sports сбрасывается по UTC.
Здесь ведём собственный журнал и НЕ ДАЁМ воркеру превысить мягкий лимит.
"""
import time
from datetime import datetime, timezone

from app import db
from app.config import DAILY_REQUEST_LIMIT, DAILY_SOFT_LIMIT, RESERVE_FOR_DETAILS

# Приоритеты задач: чем меньше число, тем важнее. Резерв берегём для 'detail'.
PRIORITY = {
    "live": 0,
    "fixtures_today": 1,
    "detail": 2,
    "fixtures_around": 3,
    "standings": 4,
    "fixtures_horizon": 5,
    "players": 6,
    "h2h": 7,
}


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def used_today() -> int:
    """Сколько запросов израсходовано сегодня.

    Главный источник правды — заголовок x-ratelimit-requests-remaining от самого API.
    К нему прибавляем запросы, сделанные уже после него (ошибки заголовок не присылают).
    """
    day = today_utc()
    anchor = db.query_one(
        """SELECT id, remaining FROM api_calls
           WHERE day=? AND remaining IS NOT NULL ORDER BY id DESC LIMIT 1""", (day,))
    if anchor:
        after = db.query_one(
            "SELECT COUNT(*) n FROM api_calls WHERE day=? AND id > ? AND status >= 200",
            (day, anchor["id"]))["n"]
        return max(0, DAILY_REQUEST_LIMIT - int(anchor["remaining"])) + after
    row = db.query_one("SELECT COUNT(*) AS n FROM api_calls WHERE day=? AND status >= 200", (day,))
    return row["n"] if row else 0


def remaining() -> int:
    return max(0, DAILY_SOFT_LIMIT - used_today())


def can_spend(task: str) -> bool:
    """Хватит ли бюджета на задачу с учётом резерва под карточки матчей."""
    left = remaining()
    if left <= 0:
        return False
    # Всё, кроме live и деталей, обязано оставить резерв нетронутым.
    if task not in ("live", "detail", "fixtures_today") and left <= RESERVE_FOR_DETAILS:
        return False
    return True


def log_call(task: str, endpoint: str, params: dict, status: int,
             results: int = 0, remaining_header=None, error: str | None = None) -> None:
    db.execute(
        """INSERT INTO api_calls(day, ts, task, endpoint, params, status, results, remaining, error)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (today_utc(), int(time.time()), task, endpoint, str(params), status,
         results, remaining_header, error),
    )


def stats() -> dict:
    used = used_today()
    rows = db.query(
        "SELECT task, COUNT(*) n FROM api_calls WHERE day=? AND status >= 200 GROUP BY task ORDER BY n DESC",
        (today_utc(),),
    )
    last = db.query_one("SELECT remaining FROM api_calls WHERE day=? AND remaining IS NOT NULL ORDER BY id DESC LIMIT 1",
                        (today_utc(),))
    return {
        "day": today_utc(),
        "used": used,
        "soft_limit": DAILY_SOFT_LIMIT,
        "hard_limit": DAILY_REQUEST_LIMIT,
        "remaining": remaining(),
        "api_remaining": last["remaining"] if last else None,
        "by_task": {r["task"]: r["n"] for r in rows},
    }
