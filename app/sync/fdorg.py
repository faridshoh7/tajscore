"""Импорт из football-data.org — основной источник по топ-лигам.

Разделение труда между двумя API:
  * football-data.org (10 запросов в минуту, суточного потолка нет) ведёт
    8 европейских турниров: расписание сезона, настоящие турнирные таблицы,
    бомбардиров и живой счёт;
  * API-Football (всего 92 запроса в сутки) бережётся для Лигаи Олӣ и тех
    шести лиг, которых у football-data нет.

Оба источника пишут в одни таблицы, поэтому здесь решаются две задачи:
  * команды сопоставляются по нормализованному имени, а не по id
    (id у источников разные и напрямую несравнимы);
  * матч ищется по «лига + дата + пара команд», чтобы один и тот же матч,
    пришедший из обоих источников, не задвоился.
Новым записям выдаются id из отдельного диапазона — пересечься с
API-Football они не могут.
"""
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from app import db
from app.config import SEASON_BY_LEAGUE
from app.sync.fd_client import fd

log = logging.getLogger("tajscore.fdorg")

# Диапазоны id, чтобы не столкнуться с нумерацией API-Football
TEAM_OFFSET = 900_000
FIXTURE_OFFSET = 900_000_000

# Наш id лиги -> код соревнования у football-data.org.
# Лиг, которых у них нет (Лигаи Олӣ, ЛЕ, Лига конференций, РПЛ, MLS), здесь нет.
COMPETITIONS = {
    2:   "CL",   # Лига чемпионов
    39:  "PL",   # Премьер-лига
    140: "PD",   # Ла Лига
    135: "SA",   # Серия А
    78:  "BL1",  # Бундеслига
    61:  "FL1",  # Лига 1
    1:   "WC",   # Чемпионат мира
    4:   "EC",   # Евро
}
LEAGUE_BY_CODE = {v: k for k, v in COMPETITIONS.items()}

# Их статусы -> наши (те же, что у API-Football)
STATUS = {
    "SCHEDULED": ("NS", "Not Started"),
    "TIMED":     ("NS", "Not Started"),
    "IN_PLAY":   ("2H", "Second Half"),
    "PAUSED":    ("HT", "Halftime"),
    "FINISHED":  ("FT", "Match Finished"),
    "SUSPENDED": ("SUSP", "Match Suspended"),
    "POSTPONED": ("PST", "Match Postponed"),
    "CANCELLED": ("CANC", "Match Cancelled"),
    "AWARDED":   ("AWD", "Technical Loss"),
}

_SUFFIXES = r"\b(fc|afc|cf|sc|ac|as|ss|ssc|us|ud|cd|rc|sv|tsv|vfl|vfb|bsc|if|ik|fk|nk|hk)\b"

# Сокращения и локальные прозвища: из написания их не вывести никаким правилом.
# Ключ — уже нормализованная форма, значение — нормализованное каноническое имя.
ALIASES = {
    "hsv": "hamburger",
    "psg": "paris saint germain",
    "barca": "barcelona",
    "m gladbach": "borussia monchengladbach",
    "gladbach": "borussia monchengladbach",
    "stade rennais": "rennes",
    "atleti": "atletico madrid",
    "man city": "manchester city",
    "man united": "manchester united",
    "spurs": "tottenham",
    "wolves": "wolverhampton wanderers",
    "inter": "internazionale",
}


def normalize(name: str) -> str:
    """«Liverpool FC», «Liverpool» и «Málaga»/«Malaga» — приводим к общему виду.

    Диакритика снимается: источники пишут одни и те же клубы то с ней, то без.
    """
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", "and").replace("-", " ").replace("'", " ")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(_SUFFIXES, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def _team_index() -> dict[str, int]:
    """Сопоставление «нормализованное имя -> id» по всем известным командам."""
    return {normalize(r["name"]): r["id"] for r in db.query("SELECT id, name FROM teams")}


def _resolve_team(conn, idx: dict, t: dict) -> int | None:
    """Находит команду по имени, иначе заводит новую в своём диапазоне id."""
    if not t:
        return None
    name = t.get("shortName") or t.get("name")
    key = normalize(name)
    if not key:
        return None
    if key in idx:
        tid = idx[key]
        # лого у football-data бывает там, где у API-Football пусто
        if t.get("crest"):
            conn.execute("UPDATE teams SET logo=COALESCE(logo, ?) WHERE id=?", (t["crest"], tid))
        return tid
    if not t.get("id"):
        return None
    tid = TEAM_OFFSET + int(t["id"])
    conn.execute(
        """INSERT INTO teams (id, name, logo) VALUES (?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, logo=excluded.logo""",
        (tid, name, t.get("crest")))
    idx[key] = tid
    return tid


def _existing_fixture(league_id: int, hid: int, aid: int, ts: int) -> int | None:
    """Тот же матч мог прийти из API-Football. Ищем в пределах суток."""
    row = db.query_one(
        """SELECT id FROM fixtures
           WHERE league_id=? AND home_id=? AND away_id=? AND ABS(timestamp - ?) < 86400""",
        (league_id, hid, aid, ts))
    return row["id"] if row else None


def _ts(date_utc: str) -> int:
    if not date_utc:
        return 0
    try:
        dt = datetime.strptime(date_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0


def _save_matches(items: list[dict], league_id: int | None = None,
                  season: int | None = None) -> int:
    """Записывает список матчей. league_id=None — берём из поля competition.

    Возвращает число записанных. Матчи турниров, которых нет в COMPETITIONS,
    пропускаются молча: сквозной эндпоинт отдаёт все 12 турниров тарифа.
    """
    now = int(time.time())
    idx = _team_index()
    n = 0
    with db.write() as conn:
        for m in items:
            lid = league_id
            if lid is None:
                lid = LEAGUE_BY_CODE.get((m.get("competition") or {}).get("code"))
            if lid is None:
                continue
            sea = season or (m.get("season") or {}).get("startDate", "")[:4] \
                or SEASON_BY_LEAGUE.get(lid)
            try:
                sea = int(sea)
            except (TypeError, ValueError):
                sea = SEASON_BY_LEAGUE.get(lid)

            st_short, st_long = STATUS.get(m.get("status"), ("NS", m.get("status") or ""))
            hid = _resolve_team(conn, idx, m.get("homeTeam"))
            aid = _resolve_team(conn, idx, m.get("awayTeam"))
            if not hid or not aid:
                continue
            date_utc = m.get("utcDate") or ""
            ts = _ts(date_utc)
            score = m.get("score") or {}
            ft = score.get("fullTime") or {}
            ht = score.get("halfTime") or {}
            w = score.get("winner")
            winner = {"HOME_TEAM": "home", "AWAY_TEAM": "away", "DRAW": "draw"}.get(w)
            rnd = f"Matchday {m['matchday']}" if m.get("matchday") else (m.get("stage") or "")

            fid = _existing_fixture(lid, hid, aid, ts) or FIXTURE_OFFSET + int(m["id"])
            conn.execute(
                """INSERT INTO fixtures (id, league_id, season, round, date_utc, timestamp,
                        status_short, status_long, home_id, away_id, home_goals, away_goals,
                        ht_home, ht_away, ft_home, ft_away, winner, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                        round=excluded.round, date_utc=excluded.date_utc,
                        timestamp=excluded.timestamp,
                        status_short=excluded.status_short, status_long=excluded.status_long,
                        home_goals=excluded.home_goals, away_goals=excluded.away_goals,
                        ht_home=excluded.ht_home, ht_away=excluded.ht_away,
                        ft_home=excluded.ft_home, ft_away=excluded.ft_away,
                        winner=excluded.winner, updated_at=excluded.updated_at""",
                (fid, lid, sea, rnd, date_utc, ts, st_short, st_long, hid, aid,
                 ft.get("home"), ft.get("away"), ht.get("home"), ht.get("away"),
                 ft.get("home"), ft.get("away"), winner, now))
            n += 1
    return n



def _cooldown(key: str, reason: str) -> None:
    """Данных нет (нет доступа к сезону, пустой ответ) — ставим отметку, чтобы
    воркер подождал обычный интервал, а не долбил эндпоинт каждые пять секунд."""
    db.mark_sync(key, ok=True, note=f"нет данных: {reason}")


# ------------------------------------------------------------------ окно дат
async def sync_window(days_back: int = 1, days_fwd: int = 7) -> int:
    """Матчи всех доступных турниров за окно дат — ОДНИМ запросом.

    Это рабочая лошадь живого режима: за один запрос приходят и счёт идущих
    матчей, и расписание ближайших дней по всем восьми лигам.
    """
    today = datetime.now(timezone.utc).date()
    params = {
        "dateFrom": (today - timedelta(days=days_back)).isoformat(),
        "dateTo": (today + timedelta(days=days_fwd)).isoformat(),
    }
    data = await fd.get("/matches", params)
    if not data:
        return 0
    n = _save_matches(data.get("matches") or [])
    db.mark_sync("fdorg:window", ok=True, note=f"{n} матчей")
    return n


# ------------------------------------------------------------------ сезон целиком
async def import_matches(league_id: int, season: int | None = None) -> int:
    """Тянет ВСЕ матчи соревнования за сезон и пишет их в fixtures."""
    code = COMPETITIONS.get(league_id)
    if not code:
        log.info("лига %s не покрывается football-data.org", league_id)
        return 0
    season = season or SEASON_BY_LEAGUE.get(league_id)
    # У них сезон обозначается годом старта: сезон 2026/27 -> 2026
    data = await fd.get(f"/competitions/{code}/matches", {"season": season})
    if not data:
        _cooldown(f"fdorg:matches:{league_id}", "расписание недоступно")
        return 0
    n = _save_matches(data.get("matches") or [], league_id, season)
    db.mark_sync(f"fdorg:matches:{league_id}", ok=True, note=f"{n} матчей")
    log.info("football-data: лига %s — записано %s матчей", league_id, n)
    return n


async def import_teams(league_id: int, season: int | None = None) -> int:
    """Полный состав участников — чтобы таблица была даже до первого тура."""
    code = COMPETITIONS.get(league_id)
    if not code:
        return 0
    season = season or SEASON_BY_LEAGUE.get(league_id)
    data = await fd.get(f"/competitions/{code}/teams", {"season": season})
    if not data:
        return 0
    idx = _team_index()
    n = 0
    with db.write() as conn:
        for t in data.get("teams") or []:
            if _resolve_team(conn, idx, t):
                n += 1
    log.info("football-data: лига %s — команд %s", league_id, n)
    return n


# ------------------------------------------------------------------ таблица
_FORM = {"W": "W", "D": "D", "L": "L"}


async def import_standings(league_id: int, season: int | None = None) -> int:
    """Настоящая турнирная таблица — то, чего бесплатный API-Football не даёт.

    Локальный расчёт из собранных матчей заведомо беднее: он не знает о снятых
    очках и технических поражениях. Поэтому для этих восьми лиг таблица берётся
    отсюда, а analytics их больше не пересчитывает (см. FD_STANDING_LEAGUES).
    """
    code = COMPETITIONS.get(league_id)
    if not code:
        return 0
    season = season or SEASON_BY_LEAGUE.get(league_id)
    data = await fd.get(f"/competitions/{code}/standings", {"season": season})
    if not data:
        _cooldown(f"standings:{league_id}", "таблица недоступна")
        return 0

    idx = _team_index()
    now = int(time.time())
    rows = []
    with db.write() as conn:
        for block in data.get("standings") or []:
            # TOTAL — общая таблица; HOME/AWAY пропускаем, они дублируют состав.
            if block.get("type") != "TOTAL":
                continue
            group = block.get("group") or ""
            # «GROUP_A» -> «Group A»: на сайте подпись показывается как есть
            if group:
                group = group.replace("_", " ").title()
            for r in block.get("table") or []:
                tid = _resolve_team(conn, idx, r.get("team"))
                if not tid:
                    continue
                form = "".join(_FORM.get(x.strip().upper(), "")
                               for x in (r.get("form") or "").split(","))[-5:]
                rows.append((
                    league_id, season, group, tid, r.get("position"),
                    r.get("playedGames"), r.get("won"), r.get("draw"), r.get("lost"),
                    r.get("goalsFor"), r.get("goalsAgainst"), r.get("goalDifference"),
                    r.get("points"), form, None, now))
        if rows:
            conn.execute("DELETE FROM standings WHERE league_id=? AND season=?",
                         (league_id, season))
            conn.executemany(
                """INSERT OR REPLACE INTO standings (league_id, season, group_name, team_id,
                       rank, played, win, draw, lose, gf, ga, gd, points, form,
                       description, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    if not rows:
        _cooldown(f"standings:{league_id}", "таблица пуста")
        return 0
    db.mark_sync(f"standings:{league_id}", ok=True, note=f"{len(rows)} строк (football-data)")
    log.info("football-data: таблица лиги %s — %s строк", league_id, len(rows))
    return len(rows)


# ------------------------------------------------------------------ бомбардиры
async def import_scorers(league_id: int, season: int | None = None) -> dict:
    """Бомбардиры и ассистенты за весь сезон.

    Локальный расчёт видит только матчи с загруженными событиями (на free-тарифе
    их единицы), поэтому эти строки помечаются source='fdorg' и пересчётом
    в analytics не затираются.
    """
    code = COMPETITIONS.get(league_id)
    if not code:
        return {}
    season = season or SEASON_BY_LEAGUE.get(league_id)
    data = await fd.get(f"/competitions/{code}/scorers", {"season": season, "limit": 50})
    if not data:
        _cooldown(f"fdorg:scorers:{league_id}", "бомбардиры недоступны")
        return {}

    idx = _team_index()
    rows = data.get("scorers") or []
    out = {}
    for category, field in (("goals", "goals"), ("assists", "assists")):
        items = [x for x in rows if x.get(field)]
        items.sort(key=lambda x: -(x.get(field) or 0))
        with db.write() as conn:
            conn.execute("DELETE FROM player_stats WHERE league_id=? AND season=? AND category=?",
                         (league_id, season, category))
            for rank, x in enumerate(items, 1):
                p, tm = x.get("player") or {}, x.get("team") or {}
                tid = idx.get(normalize(tm.get("shortName") or tm.get("name")))
                conn.execute(
                    """INSERT OR REPLACE INTO player_stats (league_id, season, category, rank,
                          player_id, name, team_id, team_name, team_logo, value, games, source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'fdorg')""",
                    (league_id, season, category, rank, p.get("id"), p.get("name"), tid,
                     tm.get("shortName") or tm.get("name"), tm.get("crest"),
                     x.get(field), x.get("playedMatches")))
        out[category] = len(items)
    db.mark_sync(f"fdorg:scorers:{league_id}", ok=True, note=str(out))
    log.info("football-data: лига %s — бомбардиры %s", league_id, out)
    return out
