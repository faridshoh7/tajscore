"""Синхронизация матчей сборной Таджикистана.

Матчи сборных разбросаны по разным турнирам (отбор ЧМ, отбор Кубка Азии,
товарищеские, CAFA Nations Cup). API-Football позволяет запросить все матчи
команды за сезон одним запросом — ?team=1536&season=2024. Ответ содержит
настоящий league_id и название турнира; мы переписываем league_id на виртуальный
9571, а оригинальный турнир кладём в round — так на странице сборной матчи
группируются по соревнованиям.
"""
import logging
import time

from app import db
from app.api_client import PlanRestricted, api
from app.config import NATIONAL_TEAM
from app.sync.store import _team

log = logging.getLogger("tajscore.sync.national")

LEAGUE_ID = NATIONAL_TEAM["league_id"]
TEAM_ID = NATIONAL_TEAM["team_id"]
SEASONS = NATIONAL_TEAM["seasons"]


def save_nt_fixtures(items: list[dict]) -> int:
    """Сохраняет матчи сборной под виртуальным league_id=9571."""
    now = int(time.time())
    n = 0
    with db.write() as conn:
        for it in items:
            fx = it.get("fixture") or {}
            lg = it.get("league") or {}
            if not fx.get("id"):
                continue
            teams_d = it.get("teams") or {}
            goals = it.get("goals") or {}
            score = it.get("score") or {}
            home, away = teams_d.get("home") or {}, teams_d.get("away") or {}
            hid, aid = _team(conn, home), _team(conn, away)
            if hid != TEAM_ID and aid != TEAM_ID:
                continue
            st = fx.get("status") or {}
            venue = fx.get("venue") or {}
            ht, ftm = score.get("halftime") or {}, score.get("fulltime") or {}
            et, pen = score.get("extratime") or {}, score.get("penalty") or {}
            winner = ("home" if home.get("winner") else
                      ("away" if away.get("winner") else
                       ("draw" if home.get("winner") is False and away.get("winner") is False else None)))
            comp_name = lg.get("name") or "—"
            conn.execute(
                """INSERT INTO fixtures (id, league_id, season, round, date_utc, timestamp,
                        status_short, status_long, elapsed, extra_minute, venue_name, venue_city,
                        referee, home_id, away_id, home_goals, away_goals,
                        ht_home, ht_away, ft_home, ft_away, et_home, et_away,
                        pen_home, pen_away, winner, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                        league_id=excluded.league_id, season=excluded.season, round=excluded.round,
                        date_utc=excluded.date_utc, timestamp=excluded.timestamp,
                        status_short=excluded.status_short, status_long=excluded.status_long,
                        elapsed=excluded.elapsed, extra_minute=excluded.extra_minute,
                        venue_name=excluded.venue_name, venue_city=excluded.venue_city,
                        referee=COALESCE(excluded.referee, fixtures.referee),
                        home_goals=excluded.home_goals, away_goals=excluded.away_goals,
                        ht_home=excluded.ht_home, ht_away=excluded.ht_away,
                        ft_home=excluded.ft_home, ft_away=excluded.ft_away,
                        et_home=excluded.et_home, et_away=excluded.et_away,
                        pen_home=excluded.pen_home, pen_away=excluded.pen_away,
                        winner=excluded.winner, updated_at=excluded.updated_at""",
                (fx["id"], LEAGUE_ID, lg.get("season"), comp_name, fx.get("date"),
                 fx.get("timestamp"), st.get("short"), st.get("long"), st.get("elapsed"),
                 st.get("extra"), venue.get("name"), venue.get("city"), fx.get("referee"),
                 hid, aid, goals.get("home"), goals.get("away"),
                 ht.get("home"), ht.get("away"), ftm.get("home"), ftm.get("away"),
                 et.get("home"), et.get("away"), pen.get("home"), pen.get("away"), winner, now),
            )
            n += 1
    return n


async def sync() -> int:
    """Запрашивает все матчи сборной за каждый сезон из конфигурации."""
    total = 0
    for season in SEASONS:
        try:
            resp = await api.get("/fixtures", {"team": TEAM_ID, "season": season}, "tj_fixtures")
        except PlanRestricted:
            log.warning("Сборная: сезон %s закрыт тарифом, пропускаем", season)
            continue
        if resp is None:
            continue
        n = save_nt_fixtures(resp)
        total += n
        log.info("Сборная Таджикистана: сезон %s — %s матчей из %s", season, n, len(resp))
    db.mark_sync("national_team", ok=True, note=f"{total} матчей")
    return total
