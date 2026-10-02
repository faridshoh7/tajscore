"""Фоновые воркеры: единственные, кто ходит в API. Сайт читает только SQLite.

Источников два, и у них несовместимые ограничения, поэтому циклов тоже два и
крутятся они независимо:

  football-data.org — 10 запросов в минуту, суточного потолка нет. Ведёт восемь
    европейских турниров: живой счёт, расписание, настоящие таблицы, бомбардиров.
    Опрашивается часто, экономить незачем.

  API-Football — всего 92 запроса в сутки. Бережётся для Лигаи Олӣ и шести лиг,
    которых у football-data нет. Расход делится на корзины (см. app/budget.py):
    в день с матчами Лигаи Олӣ ей достаётся 50 запросов на живой счёт, в пустой
    день они переходят остальным.

Шаги внутри каждого цикла упорядочены по важности, и за один тик выполняется
максимум один запросоёмкий шаг — так бюджет тратится ровно, без всплесков.
"""
import asyncio
import logging
import time

from app import analytics, budget, db, photos, wikidata
from app.api_client import BudgetExceeded, PlanRestricted, api
from app.config import (BACKFILL_ENABLED, BACKFILL_PER_DAY, DETAILS_PER_DAY,
                        FD_SYNC, FIXTURE_DAYS_AHEAD, FIXTURE_DAYS_BEHIND,
                        NATIONAL_TEAM, ODDS, PHOTOS, PRIMARY_LEAGUE_ID, SYNC,
                        USE_API_PLAYER_STATS, USE_API_STANDINGS, USER_DETAILS_PER_DAY)
from app.sync import fdorg, national, odds, tasks
from app.sync.fd_client import fd

log = logging.getLogger("tajscore.worker")

# Очередь карточек матчей: сайт кладёт id, воркер разгребает
_detail_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=100)
_queued: set[int] = set()
_state = {"running": False, "last_tick": 0, "live_mode": False, "last_live": 0,
          "primary_live": False}
_fd_state = {"running": False, "last_tick": 0, "live_mode": False, "last_window": 0}


_loop: asyncio.AbstractEventLoop | None = None


def request_detail(fixture_id: int) -> bool:
    """Вызывается из FastAPI, когда пользователь открыл страницу матча.

    Запрос карточки стоит единицу из 92 дневных, поэтому фильтров несколько:
    только матчи API-Football (у football-data своих карточек нет), только
    уже известные нам матчи (иначе перебором id можно сжечь лимит) и не больше
    USER_DETAILS_PER_DAY в сутки.
    """
    if not tasks.is_api_football_fixture(fixture_id):
        return False
    if fixture_id in _queued or _detail_queue.full():
        return False
    row = db.query_one(
        "SELECT league_id, status_short, detail_synced_at, timestamp FROM fixtures WHERE id=?",
        (fixture_id,))
    if row is None or row["league_id"] in fdorg.COMPETITIONS or not tasks.detail_is_stale(row):
        return False
    if _spent_on("tj_detail") + _spent_on("detail_user") >= USER_DETAILS_PER_DAY:
        return False
    _queued.add(fixture_id)
    # Эндпоинт FastAPI синхронный и работает в пуле потоков, а asyncio.Queue
    # не потокобезопасна — кладём в очередь из её собственного цикла.
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_enqueue, fixture_id)
    else:
        _enqueue(fixture_id)
    return True


def _enqueue(fixture_id: int) -> None:
    try:
        _detail_queue.put_nowait(fixture_id)
    except asyncio.QueueFull:
        _queued.discard(fixture_id)


def _paced_interval(task: str, base: int, window_end: int, reserve: int = 0) -> int | None:
    """Шаг опроса, при котором остатка корзины хватит до конца живого окна.

    Матчи тура часто идут в разное время (14:00, 16:00, 18:00), и при фиксированном
    шаге в 3 минуты 50 запросов кончались бы посреди последней игры. Здесь шаг
    растягивается: оставшееся время окна делим на оставшиеся запросы.
    reserve — сколько запросов не трогать (расписание на завтра тоже нужно).
    None — тратить больше нечего.
    """
    left = budget.pool_remaining(budget.pool_of(task), active_pools()) - reserve
    if left <= 0:
        return None
    span = max(0, window_end - int(time.time()))
    return max(base, int(span / left))


def active_pools() -> set[str]:
    """Корзины, которые сегодня вообще могут понадобиться.

    Спящие отдают свою квоту работающим, поэтому набор пересчитывается каждый
    раз: матч Лигаи Олӣ мог появиться в расписании уже после полуночи.
    """
    pools = {"tj", "other"}
    if tasks.primary_has_matches_today():
        pools.add("tj_live")
    return pools


def status() -> dict:
    return {**_state, "queue": _detail_queue.qsize(),
            "budget": budget.stats(active_pools()),
            "fd": {**_fd_state, "available_minute": fd.last_available},
            "backfill": tasks.backfill_progress()}


# ------------------------------------------------------------------ общее
def _due(key: str, interval: int) -> bool:
    return int(time.time()) - db.get_sync_state(key)["last_ok"] >= interval


def _spent_on(task: str) -> int:
    row = db.query_one("SELECT COUNT(*) n FROM api_calls WHERE day=? AND task=? AND error IS NULL",
                       (budget.today_utc(), task))
    return row["n"] if row else 0


# ================================================================== API-Football
async def _step_live() -> bool:
    """Живой счёт. Частота зависит от того, играет ли сейчас Лигаи Олӣ.

    Запрос ?live=all один и тот же в обоих случаях, разнятся только интервал и
    корзина, из которой он оплачен.
    """
    primary = tasks.primary_live_active()
    active = primary or tasks.live_mode_active()
    _state["live_mode"] = active
    _state["primary_live"] = primary

    if primary:
        task = "tj_live"
        interval = _paced_interval(task, SYNC["primary_live_interval"],
                                   tasks.live_window_end([PRIMARY_LEAGUE_ID]))
    elif active:
        task = "live"
        interval = _paced_interval(task, SYNC["live_interval"],
                                   tasks.live_window_end(tasks.OWN_LEAGUE_IDS), reserve=3)
    else:
        interval, task = SYNC["live_idle_interval"], "live"
    _state["live_interval"] = interval
    if interval is None:          # корзина пуста — до завтра живой счёт не тянем
        return False

    if int(time.time()) - _state["last_live"] < interval:
        return False
    _state["last_live"] = int(time.time())
    if not active:
        # матчей нет — тратить запрос незачем, только подчищаем зависшие статусы
        return await tasks.finalize_stale_live() > 0
    await tasks.sync_live(task)
    await tasks.finalize_stale_live()
    return True


async def _step_fixtures() -> bool:
    """Расписание. Один запрос по дате отдаёт матчи всего мира, включая Лигаи Олӣ."""
    today = tasks.utc_date(0)
    if _due(f"fixtures:{today}", SYNC["fixtures_today_interval"]):
        await tasks.sync_fixtures_date(today, "tj_fixtures")
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
        # карточка матча главной лиги оплачивается из её корзины
        row = db.query_one("SELECT league_id FROM fixtures WHERE id=?", (fid,))
        primary = bool(row and row["league_id"] == PRIMARY_LEAGUE_ID)
        await tasks.sync_detail(fid, task="tj_detail" if primary else "detail_user")
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


async def _step_national_team() -> bool:
    """Матчи сборной Таджикистана — раз в 12 часов."""
    if not _due("national_team", NATIONAL_TEAM["interval"]):
        return False
    await national.sync()
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
         _step_national_team, _step_backfill_dates, _step_backfill_details)


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
    global _loop
    _loop = asyncio.get_running_loop()
    _state["running"] = True
    log.info("Воркер API-Football запущен. Бюджет: %s", budget.stats(active_pools()))
    try:
        while True:
            _state["last_tick"] = int(time.time())
            await tick()
            # пересчёт таблиц — чистый CPU и SQLite; в цикле событий он
            # подвешивал бы ответы сайта, поэтому уводим в поток
            await asyncio.to_thread(_recompute_if_due)
            await asyncio.sleep(SYNC["tick"])
    except asyncio.CancelledError:
        log.info("Воркер API-Football остановлен")
        raise
    finally:
        _state["running"] = False
        await api.close()


# ================================================================== football-data.org
async def _fd_step_window() -> bool:
    """Живой счёт и ближайшее расписание всех восьми лиг — одним запросом.

    Когда матчи идут, опрашиваем раз в полминуты: счёт у них приходит с
    задержкой, и единственное, что мы можем сделать, — показать его сразу, как
    только он появится.
    """
    active = _fd_live_active()
    _fd_state["live_mode"] = active
    interval = FD_SYNC["live_interval"] if active else FD_SYNC["live_idle_interval"]
    if int(time.time()) - _fd_state["last_window"] < interval:
        return False
    _fd_state["last_window"] = int(time.time())
    await fdorg.sync_window(days_back=1, days_fwd=7)
    return True


def _fd_live_active() -> bool:
    """Идут ли матчи в лигах football-data прямо сейчас."""
    return tasks._matches_in_window(list(fdorg.COMPETITIONS)) > 0


async def _fd_step_standings() -> bool:
    lid = _fd_pick_stale("standings", FD_SYNC["standings_interval"])
    if lid is None:
        return False
    await fdorg.import_standings(lid)
    return True


async def _fd_step_scorers() -> bool:
    lid = _fd_pick_stale("fdorg:scorers", FD_SYNC["scorers_interval"])
    if lid is None:
        return False
    await fdorg.import_scorers(lid)
    return True


async def _fd_step_season() -> bool:
    """Полное расписание сезона: ловит переносы матчей, которых нет в окне дат."""
    lid = _fd_pick_stale("fdorg:matches", FD_SYNC["season_interval"])
    if lid is None:
        return False
    await fdorg.import_matches(lid)
    return True


def _fd_pick_stale(prefix: str, interval: int) -> int | None:
    """Лига с самыми старыми данными, отстоявшимися дольше интервала."""
    now = int(time.time())
    best, best_ts = None, None
    for lid in fdorg.COMPETITIONS:
        ts = db.get_sync_state(f"{prefix}:{lid}")["last_ok"]
        if now - ts < interval:
            continue
        if best_ts is None or ts < best_ts:
            best, best_ts = lid, ts
    return best


async def _fd_step_names() -> bool:
    """Русские написания имён новых игроков.

    Живёт в цикле football-data, потому что к обоим футбольным API отношения не
    имеет и их лимитов не тратит: Wikidata — открытый источник. Берём маленькими
    порциями, чтобы не держать цикл и не частить чужим API.
    """
    if not _due("wikidata:names", FD_SYNC["names_interval"]):
        return False
    todo = wikidata.pending(40)
    db.mark_sync("wikidata:names", ok=True, note=f"{len(todo)} новых")
    if not todo:
        return False
    await wikidata.resolve_many(todo)
    return True



async def _fd_step_odds() -> bool:
    """Коэффициенты букмекера. Живут в этом цикле, потому что к футбольным API
    отношения не имеют и их суточных лимитов не тратят."""
    if not ODDS["enabled"] or not _due("odds", ODDS["interval"]):
        return False
    db.mark_sync("odds", ok=True, note="проверка")
    await odds.sync()
    return True



async def _fd_step_photos() -> bool:
    """Портреты игроков с Викисклада. Тоже вне футбольных API и их лимитов."""
    if not PHOTOS["enabled"] or not _due("photos", PHOTOS["interval"]):
        return False
    db.mark_sync("photos", ok=True, note="проверка")
    r = await photos.sync(PHOTOS["batch"])
    db.mark_sync("photos", ok=True, note=f"проверено {r['checked']}, загружено {r['found']}")
    return r["checked"] > 0


FD_STEPS = (_fd_step_window, _fd_step_standings, _fd_step_scorers, _fd_step_season,
            _fd_step_names, _fd_step_odds, _fd_step_photos)


async def fd_tick() -> None:
    for step in FD_STEPS:
        try:
            if await step():
                return
        except Exception:
            log.exception("Ошибка в шаге football-data %s", step.__name__)


async def fd_run_forever() -> None:
    _fd_state["running"] = True
    log.info("Воркер football-data запущен (лиг: %s)", len(fdorg.COMPETITIONS))
    try:
        while True:
            _fd_state["last_tick"] = int(time.time())
            await fd_tick()
            await asyncio.sleep(FD_SYNC["tick"])
    except asyncio.CancelledError:
        log.info("Воркер football-data остановлен")
        raise
    finally:
        _fd_state["running"] = False
        await fd.close()
        await odds.fetcher.close()
        await photos.fetcher.close()
