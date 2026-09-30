"""Фоновый воркер: единственный, кто ходит в API. Сайт читает только SQLite.

Логика приоритетов на каждом тике:
  1) live-опрос, если по расписанию сейчас идут матчи;
  2) расписание на сегодня / вчера-завтра / горизонт +7 дней;
  3) очередь карточек матчей (её наполняет сайт, когда юзер открывает матч);
  4) турнирные таблицы по ротации;
  5) статистика игроков по ротации.
Всё, что не влезло в дневной бюджет, просто откладывается до завтра.
"""
import asyncio
import logging
import time

from app import analytics, budget, db
from app.api_client import BudgetExceeded, PlanRestricted, api
from app.config import (BACKFILL_ENABLED, BACKFILL_PER_DAY, DETAILS_PER_DAY,
                        FIXTURE_DAYS_AHEAD, FIXTURE_DAYS_BEHIND, SYNC,
                        USE_API_PLAYER_STATS, USE_API_STANDINGS)
from app.sync import tasks

log = logging.getLogger("tajscore.worker")

# Очередь карточек матчей: сайт кладёт id, воркер разгребает
_detail_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=100)
_queued: set[int] = set()
_state = {"running": False, "last_tick": 0, "live_mode": False, "last_live": 0}


def request_detail(fixture_id: int) -> bool:
    """Вызывается из FastAPI, когда пользователь открыл страницу матча."""
    if fixture_id in _queued or _detail_queue.full():
        return False
    row = db.query_one("SELECT status_short, detail_synced_at, timestamp FROM fixtures WHERE id=?",
                       (fixture_id,))
    if row is not None and not tasks.detail_is_stale(row):
        return False
    _queued.add(fixture_id)
    try:
        _detail_queue.put_nowait(fixture_id)
    except asyncio.QueueFull:
        _queued.discard(fixture_id)
        return False
    return True


def status() -> dict:
    return {**_state, "queue": _detail_queue.qsize(), "budget": budget.stats(),
            "backfill": tasks.backfill_progress()}


# ------------------------------------------------------------------ шаги
def _due(key: str, interval: int) -> bool:
    return int(time.time()) - db.get_sync_state(key)["last_ok"] >= interval


async def _step_live() -> bool:
    active = tasks.live_mode_active()
    _state["live_mode"] = active
    interval = SYNC["live_interval"] if active else SYNC["live_idle_interval"]
    if int(time.time()) - _state["last_live"] < interval:
        return False
    if not active:
        # матчей нет — тратить запрос незачем, только подчищаем зависшие статусы
        _state["last_live"] = int(time.time())
        return await tasks.finalize_stale_live() > 0
    _state["last_live"] = int(time.time())
    await tasks.sync_live()
    await tasks.finalize_stale_live()
    return True


async def _step_fixtures() -> bool:
    today = tasks.utc_date(0)
    if _due(f"fixtures:{today}", SYNC["fixtures_today_interval"]):
        await tasks.sync_fixtures_date(today, "fixtures_today")
        return True
    for off in (-1, 1):
        d = tasks.utc_date(off)
        if _due(f"fixtures:{d}", SYNC["fixtures_around_interval"]):
            await tasks.sync_fixtures_date(d, "fixtures_around")
            return True
    for off in list(range(2, FIXTURE_DAYS_AHEAD + 1)) + list(range(-FIXTURE_DAYS_BEHIND, -1)):
        d = tasks.utc_date(off)
        if _due(f"fixtures:{d}", SYNC["fixtures_horizon_interval"]):
            await tasks.sync_fixtures_date(d, "fixtures_horizon")
            return True
    return False


async def _step_details() -> bool:
    if _detail_queue.empty():
        return False
    fid = await _detail_queue.get()
    _queued.discard(fid)
    try:
        await tasks.sync_detail(fid)
    finally:
        _detail_queue.task_done()
    return True


async def _step_standings() -> bool:
    """На free-тарифе API не отдаёт таблицы текущего сезона — считаем сами, без запросов."""
    if not USE_API_STANDINGS:
        return False
    lid = tasks.pick_stale_standings()
    if lid is None:
        return False
    await tasks.sync_standings(lid)
    return True


async def _step_players() -> bool:
    if not USE_API_PLAYER_STATS:
        return False
    pick = tasks.pick_stale_players()
    if pick is None:
        return False
    await tasks.sync_players(*pick)
    return True


async def _step_backfill_dates() -> bool:
    """Добор прошедших дат сезона — из них строятся турнирные таблицы."""
    if not BACKFILL_ENABLED or _spent_on("fixtures_backfill") >= BACKFILL_PER_DAY:
        return False
    d = tasks.backfill_next_date()
    if d is None:
        return False
    await tasks.sync_fixtures_date(d, "fixtures_backfill")
    return True


async def _step_backfill_details() -> bool:
    """Остатками бюджета добираем события матчей: из них считаются бомбардиры."""
    if budget.remaining() <= 25 or _spent_on("detail") >= DETAILS_PER_DAY:
        return False
    fid = tasks.pick_match_for_details()
    if fid is None:
        return False
    await tasks.sync_detail(fid)
    return True


def _mark_blocked(step_name: str) -> None:
    """Тариф закрыл данные — помечаем задачу выполненной, чтобы не тратить запросы впустую."""
    if step_name in ("_step_fixtures", "_step_backfill_dates"):
        for off in list(range(-FIXTURE_DAYS_BEHIND, FIXTURE_DAYS_AHEAD + 1)):
            d = tasks.utc_date(off)
            st = db.get_sync_state(f"fixtures:{d}")
            if not st["last_ok"]:
                db.mark_sync(f"fixtures:{d}", ok=True, note="закрыто тарифом")


def _spent_on(task: str) -> int:
    row = db.query_one("SELECT COUNT(*) n FROM api_calls WHERE day=? AND task=? AND error IS NULL",
                       (budget.today_utc(), task))
    return row["n"] if row else 0


def _recompute_if_due() -> None:
    """Локальный пересчёт таблиц и статистики игроков. Запросов не тратит."""
    if int(time.time()) - db.get_sync_state("recompute")["last_ok"] < 600:
        return
    try:
        analytics.recompute_all()
        db.mark_sync("recompute", ok=True)
    except Exception:
        log.exception("Ошибка пересчёта таблиц")


STEPS = (_step_live, _step_fixtures, _step_details, _step_standings, _step_players,
         _step_backfill_dates, _step_backfill_details)


async def tick() -> None:
    """Один проход: выполняем максимум ОДИН запросоёмкий шаг, чтобы бюджет тратился ровно."""
    for step in STEPS:
        try:
            if await step():
                return
        except BudgetExceeded:
            log.warning("API сообщил об исчерпании лимита — пауза до завтра")
            return
        except PlanRestricted as e:
            log.warning("Тариф не даёт доступа (%s): %s", step.__name__, e)
            _mark_blocked(step.__name__)
            return
        except Exception:
            log.exception("Ошибка в шаге %s", step.__name__)


async def run_forever() -> None:
    _state["running"] = True
    log.info("Воркер запущен. Бюджет на сегодня: %s", budget.stats())
    try:
        while True:
            _state["last_tick"] = int(time.time())
            await tick()
            _recompute_if_due()
            await asyncio.sleep(SYNC["tick"])
    except asyncio.CancelledError:
        log.info("Воркер остановлен")
        raise
    finally:
        _state["running"] = False
        await api.close()
