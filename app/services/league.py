"""Страница лиги: таблица, календарь, результаты, статистика игроков, плей-офф."""
import time

from app import db
from app import photos
from app import wikidata
from app import teams_tj
from app.config import NATIONAL_TEAM, SEASON_BY_LEAGUE
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
            "team": tm["name"], "team_tg": tm["name_tg"], "team_en": tm["name_en"],
            "logo": tm["logo"],
            "played": r["played"], "win": r["win"], "draw": r["draw"], "lose": r["lose"],
            "gf": r["gf"], "ga": r["ga"], "gd": r["gd"], "points": r["points"],
            "form": list(r["form"] or ""), "zone": zone_of(r["rank"], info.get("zones")),
            "description": r["description"],
        })
    return [{"group": g or None, "rows": rws} for g, rws in groups.items()]


def fixtures(league_id: int, kind: str = "upcoming", limit: int = 60) -> list[dict]:
    is_nt = league_id == NATIONAL_TEAM["league_id"]
    q = ",".join("?" * len(FINISHED_STATUSES))
    if is_nt:
        if kind == "results":
            sql = (f"{FIXTURE_SELECT} WHERE f.league_id=? "
                   f"AND f.status_short IN ({q}) ORDER BY f.timestamp DESC LIMIT ?")
            params = (league_id, *FINISHED_STATUSES, limit)
        else:
            sql = (f"{FIXTURE_SELECT} WHERE f.league_id=? AND f.timestamp > ? "
                   f"ORDER BY f.timestamp LIMIT ?")
            params = (league_id, int(time.time()) - 10800, limit)
    else:
        season = SEASON_BY_LEAGUE.get(league_id)
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
    """Матчи, сгруппированные по турам — для календаря.

    Для сборной round = название турнира (Friendlies, Asian Cup - Qualification и т.д.)
    """
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
        d["team_name"], d["team_name_tg"] = tm["name"], tm["name_tg"]
        d["team_name_en"], d["team_logo"] = tm["name_en"], tm["logo"]
        # Имя игрока отдаём в обоих написаниях — язык выбирает фронт (tname).
        # Если в кэше его нет, обе формы останутся латиницей из API.
        d["name_en"] = d.get("name")
        d["name"] = wikidata.localize(d.get("name_en"), "ru")
        d["name_tg"] = wikidata.localize(d.get("name_en"), "tg")
        cr = photos.credit_of(d.get("name_en"))
        d["photo"] = cr["photo"] if cr else None
        d["photo_credit"] = " · ".join(filter(None, (cr.get("author"), cr.get("license")))) if cr else None
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
    is_nt = league_id == NATIONAL_TEAM["league_id"]
    return {
        "league": info,
        "standings": [] if is_nt else standings(league_id),
        "upcoming": fixtures(league_id, "upcoming", 40),
        "results": fixtures(league_id, "results", 40),
        "players": {} if is_nt else {c: players(league_id, c) for c in ("goals", "assists", "yellow", "red")},
        "bracket": [] if is_nt else (bracket(league_id) if info["group_stage"] else []),
        "coverage": {} if is_nt else analytics.coverage(league_id),
    }
