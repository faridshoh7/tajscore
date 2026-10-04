"""Учёт дневного расхода запросов к API-Football.

Бесплатный тариф = 100 запросов в сутки, счётчик у api-sports сбрасывается по UTC.
Здесь ведём собственный журнал и НЕ ДАЁМ воркеру превысить мягкий лимит.

Лимит делится на корзины (BUDGET_POOLS): отдельно Лигаи Олӣ, отдельно её живой
счёт, отдельно прочие лиги. Смысл в том, чтобы добор истории или карточки матчей
не съели запросы, на которые рассчитывает живой счёт главной лиги.

Корзина не запирает деньги намертво: неизрасходованное перетекает соседям
(см. allowance). Иначе в день без матчей Лигаи Олӣ half бюджета простаивал бы.
"""
import time
from datetime import datetime, timezone

from app import db
from app.config import (BUDGET_POOLS, DAILY_REQUEST_LIMIT, DAILY_SOFT_LIMIT,
                        RESERVE_FOR_DETAILS, TASK_POOL)

# Приоритеты задач: чем меньше число, тем важнее. Резерв берегём для 'detail'.
PRIORITY = {
    "tj_live": 0,
    "live": 1,
    "tj_fixtures": 1,
    "fixtures_today": 2,
    "tj_detail": 2,
    "detail": 3,
    "detail_user": 3,
    "fixtures_around": 4,
    "standings": 5,
    "fixtures_horizon": 6,
    "players": 7,
    "h2h": 8,
}

# Корзины, которые имеют право тратить резерв под карточки матчей.
_RESERVE_FREE = ("tj", "tj_live")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def pool_of(task: str) -> str:
    return TASK_POOL.get(task, "other")


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


def used_by_pool() -> dict[str, int]:
    rows = db.query(
        "SELECT task, COUNT(*) n FROM api_calls WHERE day=? AND status >= 200 GROUP BY task",
        (today_utc(),))
    out = {p: 0 for p in BUDGET_POOLS}
    for r in rows:
        out[pool_of(r["task"])] = out.get(pool_of(r["task"]), 0) + r["n"]
    return out


def remaining() -> int:
    return max(0, DAILY_SOFT_LIMIT - used_today())


def allowance(pool: str, active_pools: set[str] | None = None) -> int:
    """Сколько запросов корзина вправе потратить сегодня.

    Квоты простаивающих корзин делятся между работающими. active_pools — те, что
    сегодня вообще могут понадобиться; корзины вне этого набора считаются спящими
    и отдают свою квоту. Так в день без матчей Лигаи Олӣ её 50 live-запросов
    достаются прочим лигам, а не пропадают.
    """
    base = BUDGET_POOLS.get(pool, 0)
    if active_pools is None or pool not in active_pools:
        return base
    idle = sum(v for p, v in BUDGET_POOLS.items() if p not in active_pools)
    if not idle:
        return base
    active_base = sum(BUDGET_POOLS[p] for p in active_pools if p in BUDGET_POOLS)
    if active_base <= 0:
        return base
    return base + int(idle * base / active_base)


def pool_remaining(pool: str, active_pools: set[str] | None = None) -> int:
    return max(0, allowance(pool, active_pools) - used_by_pool().get(pool, 0))


def can_spend(task: str, active_pools: set[str] | None = None) -> bool:
    """Хватит ли общего бюджета и квоты корзины на эту задачу."""
    left = remaining()
    if left <= 0:
        return False
    pool = pool_of(task)
    if pool_remaining(pool, active_pools) <= 0:
        return False
    # Резерв под карточки матчей трогают только Лигаи Олӣ и самые срочные задачи.
    if pool not in _RESERVE_FREE and task not in ("live", "detail", "detail_user", "fixtures_today") \
            and left <= RESERVE_FOR_DETAILS:
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


def stats(active_pools: set[str] | None = None) -> dict:
    used = used_today()
    rows = db.query(
        "SELECT task, COUNT(*) n FROM api_calls WHERE day=? AND status >= 200 GROUP BY task ORDER BY n DESC",
        (today_utc(),),
    )
    last = db.query_one("SELECT remaining FROM api_calls WHERE day=? AND remaining IS NOT NULL ORDER BY id DESC LIMIT 1",
                        (today_utc(),))
    by_pool = used_by_pool()
    return {
        "day": today_utc(),
        "used": used,
        "soft_limit": DAILY_SOFT_LIMIT,
        "hard_limit": DAILY_REQUEST_LIMIT,
        "remaining": remaining(),
        "api_remaining": last["remaining"] if last else None,
        "by_task": {r["task"]: r["n"] for r in rows},
        "pools": {
            p: {"used": by_pool.get(p, 0),
                "allowance": allowance(p, active_pools),
                "left": pool_remaining(p, active_pools)}
            for p in BUDGET_POOLS
        },
    }
