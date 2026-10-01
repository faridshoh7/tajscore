"""Страница матча: события, статистика, составы, форма команд, личные встречи."""
from app import db
from app import wikidata
from app.services import league as league_svc
from app.sync import odds as odds_svc
from app import teams_tj
from app.services.common import (FINISHED_STATUSES, FIXTURE_SELECT, fixture_row,
                                 league_info, phase)

# Ключи статистики API -> ключи переводов на фронте
STAT_KEYS = {
    "Ball Possession": "stat.possession",
    "Total Shots": "stat.shots_total",
    "Shots on Goal": "stat.shots_on",
    "Shots off Goal": "stat.shots_off",
    "Blocked Shots": "stat.shots_blocked",
    "Shots insidebox": "stat.shots_inside",
    "Shots outsidebox": "stat.shots_outside",
    "Corner Kicks": "stat.corners",
    "Offsides": "stat.offsides",
    "Fouls": "stat.fouls",
    "Yellow Cards": "stat.yellow",
    "Red Cards": "stat.red",
    "Goalkeeper Saves": "stat.saves",
    "Total passes": "stat.passes",
    "Passes accurate": "stat.passes_accurate",
    "Passes %": "stat.passes_pct",
    "expected_goals": "stat.xg",
}
STAT_ORDER = list(STAT_KEYS.keys())


def get_match(fixture_id: int) -> dict | None:
    row = db.query_one(f"{FIXTURE_SELECT} WHERE f.id=?", (fixture_id,))
    if not row:
        return None
    m = fixture_row(row)
    m["league"] = league_info(row["league_id"])
    m["referee"] = row["referee"]
    m["venue"] = row["venue_name"]
    m["venue_city"] = row["venue_city"]
    m["venue_capacity"] = row["venue_capacity"]
    m["detail_synced_at"] = row["detail_synced_at"]
    # Таблица лиги прямо на странице матча — как у Flashscore. У турниров с
    # группами оставляем только ту, где играют эти две команды: остальные
    # к матчу отношения не имеют.
    m["standings"] = _relevant_standings(row["league_id"], row["home_id"], row["away_id"])
    # Коэффициенты показываем только до начала матча: во время игры и после неё
    # они бессмысленны, а устаревшая цена хуже прочерка.
    m["odds"] = odds_svc.get(fixture_id) if m["phase"] == "scheduled" else None
    m["events"] = get_events(fixture_id)
    m["statistics"] = get_statistics(fixture_id, row["home_id"], row["away_id"])
    m["lineups"] = get_lineups(fixture_id, row["home_id"], row["away_id"])
    m["form"] = {"home": team_form(row["home_id"], row["timestamp"]),
                 "away": team_form(row["away_id"], row["timestamp"])}
    m["h2h"] = head_to_head(row["home_id"], row["away_id"], fixture_id)
    return m



def _relevant_standings(league_id: int, home_id: int, away_id: int) -> list[dict]:
    try:
        groups = league_svc.standings(league_id)
    except Exception:
        return []
    if len(groups) <= 1:
        return groups
    here = [g for g in groups
            if any(r["team_id"] in (home_id, away_id) for r in g["rows"])]
    return here or groups[:1]


def get_events(fixture_id: int) -> list[dict]:
    rows = db.query(
        """SELECT e.*, t.name team_name, t.logo team_logo FROM fixture_events e
           LEFT JOIN teams t ON t.id = e.team_id
           WHERE e.fixture_id=? ORDER BY e.minute, e.extra, e.idx""", (fixture_id,))
    out = []
    for r in rows:
        kind = "other"
        d = (r["detail"] or "")
        if r["type"] == "Goal":
            kind = "own_goal" if d == "Own Goal" else ("missed_penalty" if d == "Missed Penalty"
                   else ("penalty_goal" if d == "Penalty" else "goal"))
        elif r["type"] == "Card":
            kind = "red" if d in ("Red Card", "Second Yellow card") else "yellow"
        elif (r["type"] or "").lower() == "subst":
            kind = "subst"
        elif (r["type"] or "").lower() == "var":
            kind = "var"
        tm = teams_tj.team_out(r["team_id"], r["team_name"], r["team_logo"])
        out.append({
            "minute": r["minute"], "extra": r["extra"], "kind": kind,
            "type": r["type"], "detail": r["detail"], "comments": r["comments"],
            "team_id": r["team_id"], "team_name": tm["name"],
            "team_name_tg": tm["name_tg"], "team_logo": tm["logo"],
            "player": _person(r["player_id"], r["player_name"]),
            "assist": _person(r["assist_id"], r["assist_name"]),
        })
    return out



def _person(pid, latin: str | None) -> dict:
    """Имя человека в обоих написаниях — язык выбирает фронт (tname).
    Нет перевода в кэше — обе формы останутся латиницей из API."""
    return {"id": pid, "name": wikidata.localize(latin, "ru"),
            "name_tg": wikidata.localize(latin, "tg"), "name_en": latin}


def _player_row(p) -> dict:
    d = dict(p)
    d["name_en"] = d.get("name")
    d["name"] = wikidata.localize(d["name_en"], "ru")
    d["name_tg"] = wikidata.localize(d["name_en"], "tg")
    return d


def get_statistics(fixture_id: int, home_id: int, away_id: int) -> list[dict]:
    rows = db.query("SELECT team_id, stat_key, value FROM fixture_stats WHERE fixture_id=?",
                    (fixture_id,))
    if not rows:
        return []
    data: dict[str, dict] = {}
    for r in rows:
        data.setdefault(r["stat_key"], {})[r["team_id"]] = r["value"]
    out = []
    keys = [k for k in STAT_ORDER if k in data] + [k for k in data if k not in STAT_ORDER]
    for k in keys:
        h, a = data[k].get(home_id), data[k].get(away_id)
        if h is None and a is None:
            continue
        out.append({"key": k, "i18n": STAT_KEYS.get(k), "home": h, "away": a,
                    "percent": k in ("Ball Possession", "Passes %")})
    return out


def get_lineups(fixture_id: int, home_id: int, away_id: int) -> dict:
    out = {}
    for side, tid in (("home", home_id), ("away", away_id)):
        head = db.query_one("SELECT * FROM fixture_lineups WHERE fixture_id=? AND team_id=?",
                            (fixture_id, tid))
        players = db.query(
            """SELECT * FROM fixture_players WHERE fixture_id=? AND team_id=?
               ORDER BY is_start DESC, number""", (fixture_id, tid))
        out[side] = {
            "team_id": tid,
            "formation": head["formation"] if head else None,
            "coach": head["coach_name"] if head else None,
            "start": [_player_row(p) for p in players if p["is_start"]],
            "bench": [_player_row(p) for p in players if not p["is_start"]],
        }
    return out


def team_form(team_id: int, before_ts: int, limit: int = 5) -> list[dict]:
    """Последние матчи команды до указанного времени."""
    q = ",".join("?" * len(FINISHED_STATUSES))
    rows = db.query(
        f"""{FIXTURE_SELECT} WHERE (f.home_id=? OR f.away_id=?) AND f.timestamp < ?
            AND f.status_short IN ({q}) ORDER BY f.timestamp DESC LIMIT ?""",
        (team_id, team_id, before_ts, *FINISHED_STATUSES, limit))
    out = []
    for r in rows:
        m = fixture_row(r)
        is_home = r["home_id"] == team_id
        gf = r["home_goals"] if is_home else r["away_goals"]
        ga = r["away_goals"] if is_home else r["home_goals"]
        m["result"] = "W" if (gf or 0) > (ga or 0) else ("D" if gf == ga else "L")
        m["is_home"] = is_home
        out.append(m)
    return out


def head_to_head(home_id: int, away_id: int, exclude_id: int, limit: int = 10) -> list[dict]:
    q = ",".join("?" * len(FINISHED_STATUSES))
    rows = db.query(
        f"""{FIXTURE_SELECT}
            WHERE ((f.home_id=? AND f.away_id=?) OR (f.home_id=? AND f.away_id=?))
              AND f.id <> ? AND f.status_short IN ({q})
            ORDER BY f.timestamp DESC LIMIT ?""",
        (home_id, away_id, away_id, home_id, exclude_id, *FINISHED_STATUSES, limit))
    return [fixture_row(r) for r in rows]
