"""Задачи синхронизации: каждая = один-два запроса к API и запись в базу."""
import logging
import time
from datetime import datetime, timedelta, timezone

from app import db
from app.api_client import api
from app.config import (LEAGUE_IDS, PRIMARY_LEAGUE_ID, SEASON_BY_LEAGUE, SYNC,
                        LEAGUE_BY_ID)
from app.sync import store
from app.sync.fdorg import COMPETITIONS as FD_COMPETITIONS

# Лиги, за которые отвечает API-Football: главная плюс те, которых нет
# у football-data.org. Остальные ему не нужны — их ведёт второй источник.
OWN_LEAGUE_IDS = [lid for lid in LEAGUE_IDS if lid not in FD_COMPETITIONS]

log = logging.getLogger("tajscore.sync")

# id матчей из football-data.org и ручного импорта начинаются с 900 000 000
# (см. fdorg.FIXTURE_OFFSET). У API-Football таких матчей нет: запрос по ним
# вернёт пустоту, но всё равно спишется из дневного лимита.
FOREIGN_ID_FROM = 900_000_000


def is_api_football_fixture(fixture_id: int | None) -> bool:
    return bool(fixture_id) and 0 < int(fixture_id) < FOREIGN_ID_FROM


# Статусы, при которых матч считается идущим
LIVE_STATUSES = ("1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE")
FINISHED_STATUSES = ("FT", "AET", "PEN", "PST", "CANC", "ABD", "AWD", "WO")


def utc_date(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ расписание
async def sync_fixtures_date(date_str: str, task: str = "fixtures_today") -> int:
    """Один запрос = все матчи мира за дату. Лишние лиги отсекаем локально."""
    resp = await api.get("/fixtures", {"date": date_str}, task)
    if resp is None:
        return -1
    n = store.save_fixtures(resp)
    db.mark_sync(f"fixtures:{date_str}", ok=True, note=f"{n} матчей из {len(resp)}")
    log.info("Расписание %s: сохранено %s матчей (в ответе %s)", date_str, n, len(resp))
    return n


# ------------------------------------------------------------------ live
async def sync_live(task: str = "live") -> int:
    """Один запрос = все живые матчи мира.

    task задаёт корзину бюджета: "tj_live", когда запрос делается ради Лигаи Олӣ,
    иначе "live". Сам ответ в обоих случаях один и тот же — ?live=all отдаёт все
    матчи сразу, так что платит одна лига, а пользуются все.
    """
    resp = await api.get("/fixtures", {"live": "all"}, task)
    if resp is None:
        return -1
    n = store.save_fixtures(resp)
    db.mark_sync("live", ok=True, note=f"{n} живых матчей")
    return n


async def finalize_stale_live() -> int:
    """Матчи, зависшие в статусе «идёт», хотя время вышло: добираем итог пачкой по id.

    Параметр ids позволяет запросить до 20 матчей одним запросом.
    """
    cutoff = int(time.time()) - SYNC["live_window_after"]
    rows = db.query(
        f"""SELECT id FROM fixtures
            WHERE status_short IN ({','.join('?' * len(LIVE_STATUSES))})
              AND timestamp < ? ORDER BY timestamp LIMIT 20""",
        (*LIVE_STATUSES, cutoff),
    )
    if not rows:
        return 0
    ids = "-".join(str(r["id"]) for r in rows)
    resp = await api.get("/fixtures", {"ids": ids}, "live")
    if resp is None:
        return -1
    n = store.save_fixtures(resp)
    log.info("Добрал итоговые счета: %s матчей", n)
    return n


def _matches_in_window(league_ids) -> int:
    """Сколько матчей этих лиг попадает в живое окно: вот-вот начнутся или идут."""
    if not league_ids:
        return 0
    now = int(time.time())
    row = db.query_one(
        f"""SELECT COUNT(*) n FROM fixtures
            WHERE league_id IN ({','.join('?' * len(league_ids))})
              AND timestamp BETWEEN ? AND ?
              AND status_short NOT IN ({','.join('?' * len(FINISHED_STATUSES))})""",
        (*league_ids, now - SYNC["live_window_after"], now + SYNC["live_window_before"],
         *FINISHED_STATUSES),
    )
    return row["n"] if row else 0


def live_window_end(league_ids) -> int:
    """Когда закончится текущее живое окно этих лиг: старт последнего матча,
    который ещё не завершён и начнётся/идёт в пределах суток, плюс время игры.
    0 — окна нет."""
    if not league_ids:
        return 0
    now = int(time.time())
    row = db.query_one(
        f"""SELECT MAX(timestamp) ts FROM fixtures
            WHERE league_id IN ({','.join('?' * len(league_ids))})
              AND timestamp BETWEEN ? AND ?
              AND status_short NOT IN ({','.join('?' * len(FINISHED_STATUSES))})""",
        (*league_ids, now - SYNC["live_window_after"], now + 86400, *FINISHED_STATUSES))
    ts = row["ts"] if row and row["ts"] else 0
    return ts + SYNC["live_window_after"] if ts else 0


def live_mode_active() -> bool:
    """Есть ли смысл опрашивать live прямо сейчас (любая наша лига)."""
    return _matches_in_window(OWN_LEAGUE_IDS) > 0


def primary_live_active() -> bool:
    """Идут ли прямо сейчас матчи Лигаи Олӣ.

    От этого зависит, из какой корзины оплачивается live-запрос и как часто он
    делается: ради главной лиги опрашиваем втрое чаще, чем ради остальных.
    """
    return _matches_in_window([PRIMARY_LEAGUE_ID]) > 0


def primary_has_matches_today() -> bool:
    """Есть ли у Лигаи Олӣ матчи в текущие сутки по UTC.

    Нужно, чтобы решить, выделять ли ей корзину live на сегодня. В пустой день
    её 50 запросов достаются другим лигам.
    """
    today = utc_date(0)
    row = db.query_one(
        "SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND date_utc LIKE ?",
        (PRIMARY_LEAGUE_ID, f"{today}%"))
    return bool(row and row["n"])


# ------------------------------------------------------------------ таблицы
async def sync_standings(league_id: int) -> int:
    season = SEASON_BY_LEAGUE[league_id]
    resp = await api.get("/standings", {"league": league_id, "season": season}, "standings")
    if resp is None:
        return -1
    n = store.save_standings(league_id, season, resp)
    db.mark_sync(f"standings:{league_id}", ok=True, note=f"{n} строк")
    log.info("Таблица лиги %s: %s строк", league_id, n)
    return n


def pick_stale_standings() -> int | None:
    """Лига с самой старой таблицей, которая уже отстоялась дольше интервала."""
    now = int(time.time())
    best, best_ts = None, None
    for lid in LEAGUE_IDS:
        st = db.get_sync_state(f"standings:{lid}")
        ts = st["last_ok"]
        if now - ts < SYNC["standings_interval"]:
            continue
        # у прошедших турниров (Евро, ЧМ) таблицу тянем один раз и забываем
        if ts and LEAGUE_BY_ID[lid]["is_cup"] and not _league_has_upcoming(lid):
            continue
        if best_ts is None or ts < best_ts:
            best, best_ts = lid, ts
    return best


def _league_has_upcoming(league_id: int) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND timestamp > ?",
        (league_id, int(time.time()) - 86400 * 14))
    return bool(row and row["n"])


# ------------------------------------------------------------------ игроки
PLAYER_ENDPOINTS = {
    "goals": "/players/topscorers",
    "assists": "/players/topassists",
    "yellow": "/players/topyellowcards",
    "red": "/players/topredcards",
}


async def sync_players(league_id: int, category: str) -> int:
    season = SEASON_BY_LEAGUE[league_id]
    resp = await api.get(PLAYER_ENDPOINTS[category],
                         {"league": league_id, "season": season}, "players")
    if resp is None:
        return -1
    n = store.save_player_stats(league_id, season, category, resp)
    db.mark_sync(f"players:{league_id}:{category}", ok=True, note=f"{n} игроков")
    log.info("Игроки %s/%s: %s", league_id, category, n)
    return n


def pick_stale_players() -> tuple[int, str] | None:
    """Ротация: клубные лиги важнее, категории по очереди."""
    now = int(time.time())
    best, best_ts = None, None
    for lid in LEAGUE_IDS:
        if not _league_has_upcoming(lid):
            continue
        for cat in ("goals", "assists", "yellow", "red"):
            st = db.get_sync_state(f"players:{lid}:{cat}")
            ts = st["last_ok"]
            if now - ts < SYNC["players_interval"]:
                continue
            if best_ts is None or ts < best_ts:
                best, best_ts = (lid, cat), ts
    return best


# ------------------------------------------------------------------ карточка матча
async def sync_detail(fixture_id: int, force: bool = False,
                      task: str = "detail") -> bool:
    """Один запрос /fixtures?id= отдаёт события + составы + статистику сразу.

    task выбирает корзину бюджета: карточки матчей Лигаи Олӣ идут из её запаса,
    чтобы добор событий по чужим лигам их не вытеснил.
    """
    if not is_api_football_fixture(fixture_id):
        return False
    row = db.query_one("SELECT status_short, detail_synced_at, timestamp FROM fixtures WHERE id=?",
                       (fixture_id,))
    if row and not force and not detail_is_stale(row):
        return True
    resp = await api.get("/fixtures", {"id": fixture_id}, task)
    if resp is None:
        return False
    item = resp[0] if resp else None
    if not item:
        # API такого матча не знает — помечаем, чтобы не спрашивать снова
        store.mark_detail_synced(fixture_id)
        return False
    store.save_fixtures([item], only_known_leagues=False)
    store.save_events(fixture_id, item.get("events") or [])
    store.save_lineups(fixture_id, item.get("lineups") or [])
    store.save_statistics(fixture_id, item.get("statistics") or [])
    store.mark_detail_synced(fixture_id)
    log.info("Карточка матча %s обновлена", fixture_id)
    return True


def detail_is_stale(row) -> bool:
    """Живой матч — обновляем часто, недавно сыгранный — раз в час, финал — никогда."""
    synced = row["detail_synced_at"] or 0
    if not synced:
        return True
    age = int(time.time()) - synced
    status = row["status_short"]
    if status in LIVE_STATUSES:
        return age > SYNC["detail_live_ttl"]
    if status in FINISHED_STATUSES:
        # финальный матч перезапрашиваем только если детали собрали ДО его конца
        return synced < (row["timestamp"] or 0) + SYNC["live_window_after"]
    return age > SYNC["detail_recent_ttl"]


# ------------------------------------------------------------------ личные встречи
async def sync_h2h(team_a: int, team_b: int) -> int:
    key = f"{min(team_a, team_b)}-{max(team_a, team_b)}"
    row = db.query_one("SELECT fetched_at FROM h2h_pairs WHERE pair_key=?", (key,))
    if row and int(time.time()) - row["fetched_at"] < SYNC["h2h_ttl"]:
        return 0
    resp = await api.get("/fixtures/headtohead", {"h2h": f"{team_a}-{team_b}", "last": 10}, "h2h")
    if resp is None:
        return -1
    n = store.save_fixtures(resp, only_known_leagues=False)
    db.execute("INSERT OR REPLACE INTO h2h_pairs(pair_key, fetched_at) VALUES(?,?)",
               (key, int(time.time())))
    return n


# ------------------------------------------------------------------ добор истории
def backfill_next_date() -> str | None:
    """Самая свежая из ещё не скачанных прошедших дат сезона.

    Идём от сегодняшнего дня назад: свежая история важнее старой.
    Один запрос за дату закрывает сразу все 15 лиг.
    """
    from app.config import BACKFILL_START, BACKFILL_START_TJK
    start = min(BACKFILL_START, BACKFILL_START_TJK)
    d = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cur = today - timedelta(days=1)
    while cur >= d:
        key = f"fixtures:{cur:%Y-%m-%d}"
        if not db.get_sync_state(key)["last_ok"]:
            return f"{cur:%Y-%m-%d}"
        cur -= timedelta(days=1)
    return None


def backfill_progress() -> dict:
    from app.config import BACKFILL_START, BACKFILL_START_TJK
    start = datetime.strptime(min(BACKFILL_START, BACKFILL_START_TJK), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = (today - start).days
    done = db.query_one(
        "SELECT COUNT(*) n FROM sync_state WHERE key LIKE 'fixtures:%' AND last_ok>0")["n"]
    return {"days_total": total, "days_done": done,
            "percent": round(100 * done / total) if total else 100}


def pick_match_for_details() -> int | None:
    """Завершённый матч без деталей: сначала свежие и из приоритетных лиг.

    Из этих событий потом считаются бомбардиры, ассистенты и карточки.
    """
    # Лиги football-data сюда не берём: у API-Football их матчей под нашими id нет,
    # а события топ-лиг ему всё равно не на что тратить — таблицы и бомбардиры
    # приходят из football-data готовыми.
    fd = list(FD_COMPETITIONS)
    row = db.query_one(
        f"""SELECT f.id FROM fixtures f JOIN leagues l ON l.id = f.league_id
            WHERE f.detail_synced_at = 0 AND f.id < ?
              AND f.league_id NOT IN ({','.join('?' * len(fd))})
              AND f.status_short IN ('FT', 'AET', 'PEN')
            ORDER BY l.priority ASC, f.timestamp DESC LIMIT 1""",
        (FOREIGN_ID_FROM, *fd))
    return row["id"] if row else None
