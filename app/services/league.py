"""Страница лиги: таблица, календарь, результаты, статистика игроков, плей-офф."""
import time

from app import db
from app import teams_tj
from app.config import SEASON_BY_LEAGUE
from app.services.common import (FINISHED_STATUSES, FIXTURE_SELECT, fixture_row, league_info)

PLAYOFF_ORDER = ["Preliminary Round", "Qualifying Round", "Play-offs", "Knockout Round Play-offs",
                 "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals",
                 "3rd Place Final", "Final"]


def zone_of(rank: int, zones: dict) -> str | None:
    for name, (lo, hi) in (zones or {}).items():
        if lo and lo <= rank <= hi:
            return name
    return None


def standings(league_id: int) -> list[dict]:
    season = SEASON_BY_LEAGUE.get(league_id)
    info = league_info(league_id) or {}
    rows = db.query(
        """SELECT s.*, t.name team_name, t.logo team_logo FROM standings s
           LEFT JOIN teams t ON t.id = s.team_id
           WHERE s.league_id=? AND s.season=? ORDER BY s.group_name, s.rank""",
        (league_id, season))
    groups: dict[str, list] = {}
    for r in rows:
        tm = teams_tj.team_out(r["team_id"], r["team_name"], r["team_logo"])
        groups.setdefault(r["group_name"] or "", []).append({
            "rank": r["rank"], "team_id": r["team_id"],
            "team": tm["name"], "team_tg": tm["name_tg"], "logo": tm["logo"],
            "played": r["played"], "win": r["win"], "draw": r["draw"], "lose": r["lose"],
            "gf": r["gf"], "ga": r["ga"], "gd": r["gd"], "points": r["points"],
            "form": list(r["form"] or ""), "zone": zone_of(r["rank"], info.get("zones")),
            "description": r["description"],
        })
    return [{"group": g or None, "rows": rws} for g, rws in groups.items()]


def fixtures(league_id: int, kind: str = "upcoming", limit: int = 60) -> list[dict]:
    season = SEASON_BY_LEAGUE.get(league_id)
    q = ",".join("?" * len(FINISHED_STATUSES))
    if kind == "results":
        sql = (f"{FIXTURE_SELECT} WHERE f.league_id=? AND f.season=? "
               f"AND f.status_short IN ({q}) ORDER BY f.timestamp DESC LIMIT ?")
        params = (league_id, season, *FINISHED_STATUSES, limit)
    else:
        sql = (f"{FIXTURE_SELECT} WHERE f.league_id=? AND f.season=? AND f.timestamp > ? "
               f"ORDER BY f.timestamp LIMIT ?")
        params = (league_id, season, int(time.time()) - 10800, limit)
    return [fixture_row(r) for r in db.query(sql, params)]


def by_round(league_id: int, kind: str = "results") -> list[dict]:
    """Матчи, сгруппированные по турам — для календаря."""
    items = fixtures(league_id, kind, limit=200)
    buckets: dict[str, list] = {}
    for m in items:
        buckets.setdefault(m["round"] or "—", []).append(m)
    return [{"round": r, "matches": ms} for r, ms in buckets.items()]


def players(league_id: int, category: str = "goals", limit: int = 20) -> list[dict]:
    season = SEASON_BY_LEAGUE.get(league_id)
    rows = db.query(
        """SELECT * FROM player_stats WHERE league_id=? AND season=? AND category=?
           ORDER BY rank LIMIT ?""", (league_id, season, category, limit))
    out = []
    for r in rows:
        d = dict(r)
        tm = teams_tj.team_out(d.get("team_id"), d.get("team_name"), d.get("team_logo"))
        d["team_name"], d["team_name_tg"], d["team_logo"] = tm["name"], tm["name_tg"], tm["logo"]
        out.append(d)
    return out


def bracket(league_id: int) -> list[dict]:
    """Сетка плей-офф: матчи с раундами навылет, сгруппированные по стадиям."""
    season = SEASON_BY_LEAGUE.get(league_id)
    rows = db.query(f"{FIXTURE_SELECT} WHERE f.league_id=? AND f.season=? ORDER BY f.timestamp",
                    (league_id, season))
    stages: dict[str, list] = {}
    for r in rows:
        rnd = (r["round"] or "").strip()
        stage = next((s for s in PLAYOFF_ORDER if rnd.lower().startswith(s.lower())), None)
        if not stage:
            continue
        stages.setdefault(stage, []).append(fixture_row(r))
    return [{"stage": s, "matches": stages[s]} for s in PLAYOFF_ORDER if s in stages]


def page(league_id: int) -> dict | None:
    info = league_info(league_id)
    if not info:
        return None
    from app import analytics
    return {
        "league": info,
        "standings": standings(league_id),
        "upcoming": fixtures(league_id, "upcoming", 40),
        "results": fixtures(league_id, "results", 40),
        "players": {c: players(league_id, c) for c in ("goals", "assists", "yellow", "red")},
        "bracket": bracket(league_id) if info["group_stage"] else [],
        "coverage": analytics.coverage(league_id),
    }
