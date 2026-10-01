"""Расчёт турнирных таблиц и статистики игроков из локальной базы.

Нужен потому, что бесплатный тариф API не отдаёт /standings и /players/* по текущему
сезону. Считаем по сыгранным матчам (fixtures) и событиям (fixture_events).

Восемь лиг, которые ведёт football-data.org, здесь НЕ пересчитываются: оттуда
приходит настоящая таблица, со снятыми очками и техническими результатами,
а локальный расчёт их не знает и только испортил бы её.
"""
import time

from app import db
from app.config import LEAGUE_BY_ID, LEAGUE_IDS, SEASON_BY_LEAGUE
from app.sync.fdorg import COMPETITIONS as FD_COMPETITIONS

RESULT_STATUSES = ("FT", "AET", "PEN")


def _group_of(round_name: str | None) -> str:
    """Из названия тура достаём группу: 'Group A - 3' -> 'Group A'."""
    if not round_name:
        return ""
    r = round_name.strip()
    for sep in (" - ", " – "):
        if sep in r:
            head = r.split(sep)[0].strip()
            if head.lower().startswith("group"):
                return head
            return "" if not head.lower().startswith(("league stage", "league phase")) else head
    return r if r.lower().startswith("group") else ""


def compute_standings(league_id: int, season: int | None = None) -> int:
    """Строит таблицу лиги из сыгранных матчей. Возвращает число строк."""
    season = season or SEASON_BY_LEAGUE.get(league_id)
    rows = db.query(
        f"""SELECT id, round, home_id, away_id,
                   COALESCE(ft_home, home_goals) gh, COALESCE(ft_away, away_goals) ga, timestamp
            FROM fixtures
            WHERE league_id=? AND season=? AND status_short IN ({','.join('?' * len(RESULT_STATUSES))})
              AND home_id IS NOT NULL AND away_id IS NOT NULL
              AND home_goals IS NOT NULL
            ORDER BY timestamp""",
        (league_id, season, *RESULT_STATUSES),
    )
    # Участники сезона — из ВСЕХ матчей, включая ещё не сыгранные. Иначе до первого
    # тура таблица пустая, а команда, у которой матчи только впереди, в неё не попадает.
    entrants = db.query(
        """SELECT round, home_id, away_id FROM fixtures
           WHERE league_id=? AND season=? AND home_id IS NOT NULL AND away_id IS NOT NULL""",
        (league_id, season))
    if not rows and not entrants:
        return 0

    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM teams")}
    table: dict[tuple[str, int], dict] = {}

    def cell(group: str, team: int) -> dict:
        key = (group, team)
        if key not in table:
            table[key] = {"team_id": team, "group": group, "played": 0, "win": 0, "draw": 0,
                          "lose": 0, "gf": 0, "ga": 0, "points": 0, "form": [],
                          "name": names.get(team, "")}
        return table[key]

    # заводим строку каждому участнику — с нулями, если он ещё не играл
    for e in entrants:
        grp = _group_of(e["round"])
        cell(grp, e["home_id"])
        cell(grp, e["away_id"])

    for r in rows:
        grp = _group_of(r["round"])
        gh, ga = r["gh"], r["ga"]
        if gh is None or ga is None:
            continue
        h, a = cell(grp, r["home_id"]), cell(grp, r["away_id"])
        for side, gf_, ga_ in ((h, gh, ga), (a, ga, gh)):
            side["played"] += 1
            side["gf"] += gf_
            side["ga"] += ga_
            if gf_ > ga_:
                side["win"] += 1; side["points"] += 3; side["form"].append("W")
            elif gf_ == ga_:
                side["draw"] += 1; side["points"] += 1; side["form"].append("D")
            else:
                side["lose"] += 1; side["form"].append("L")

    now = int(time.time())
    groups: dict[str, list[dict]] = {}
    for v in table.values():
        v["gd"] = v["gf"] - v["ga"]
        groups.setdefault(v["group"], []).append(v)

    n = 0
    with db.write() as conn:
        conn.execute("DELETE FROM standings WHERE league_id=? AND season=?", (league_id, season))
        for grp, items in groups.items():
            items.sort(key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["name"] or str(x["team_id"])))
            for i, v in enumerate(items, 1):
                conn.execute(
                    """INSERT OR REPLACE INTO standings (league_id, season, group_name, team_id, rank,
                          played, win, draw, lose, gf, ga, gd, points, form, description, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (league_id, season, grp, v["team_id"], i, v["played"], v["win"], v["draw"],
                     v["lose"], v["gf"], v["ga"], v["gd"], v["points"],
                     "".join(v["form"][-5:]), None, now))
                n += 1
    db.mark_sync(f"standings:{league_id}", ok=True, note=f"{n} строк (расчёт)")
    return n


# ------------------------------------------------------------------ игроки
PLAYER_QUERIES = {
    "goals": """
        SELECT e.player_id pid, e.player_name nm, e.team_id tid, COUNT(*) val
        FROM fixture_events e JOIN fixtures f ON f.id = e.fixture_id
        WHERE f.league_id=? AND f.season=? AND e.type='Goal'
          AND e.detail NOT IN ('Missed Penalty','Own Goal') AND e.player_id IS NOT NULL
        GROUP BY e.player_id ORDER BY val DESC, nm LIMIT 50""",
    "assists": """
        SELECT e.assist_id pid, e.assist_name nm, e.team_id tid, COUNT(*) val
        FROM fixture_events e JOIN fixtures f ON f.id = e.fixture_id
        WHERE f.league_id=? AND f.season=? AND e.type='Goal'
          AND e.detail NOT IN ('Missed Penalty','Own Goal') AND e.assist_id IS NOT NULL
        GROUP BY e.assist_id ORDER BY val DESC, nm LIMIT 50""",
    "yellow": """
        SELECT e.player_id pid, e.player_name nm, e.team_id tid, COUNT(*) val
        FROM fixture_events e JOIN fixtures f ON f.id = e.fixture_id
        WHERE f.league_id=? AND f.season=? AND e.type='Card' AND e.detail='Yellow Card'
          AND e.player_id IS NOT NULL
        GROUP BY e.player_id ORDER BY val DESC, nm LIMIT 50""",
    "red": """
        SELECT e.player_id pid, e.player_name nm, e.team_id tid, COUNT(*) val
        FROM fixture_events e JOIN fixtures f ON f.id = e.fixture_id
        WHERE f.league_id=? AND f.season=? AND e.type='Card'
          AND e.detail IN ('Red Card','Second Yellow card') AND e.player_id IS NOT NULL
        GROUP BY e.player_id ORDER BY val DESC, nm LIMIT 50""",
}


def compute_player_stats(league_id: int, season: int | None = None) -> dict:
    """Считает бомбардиров/ассистентов/карточки по событиям уже загруженных матчей."""
    season = season or SEASON_BY_LEAGUE.get(league_id)
    out = {}
    for category, sql in PLAYER_QUERIES.items():
        # Данные из football-data.org покрывают весь сезон, а локальный счёт —
        # только матчи с загруженными событиями. Импорт не перетираем.
        imported = db.query_one(
            """SELECT COUNT(*) n FROM player_stats
               WHERE league_id=? AND season=? AND category=? AND source='fdorg'""",
            (league_id, season, category))["n"]
        if imported:
            out[category] = imported
            continue
        rows = db.query(sql, (league_id, season))
        with db.write() as conn:
            conn.execute("""DELETE FROM player_stats WHERE league_id=? AND season=? AND category=?
                            AND (source IS NULL OR source='calc')""",
                         (league_id, season, category))
            for rank, r in enumerate(rows, 1):
                team = db.query_one("SELECT name, logo FROM teams WHERE id=?", (r["tid"],))
                conn.execute(
                    """INSERT OR REPLACE INTO player_stats (league_id, season, category, rank,
                          player_id, name, team_id, team_name, team_logo, value, source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,'calc')""",
                    (league_id, season, category, rank, r["pid"], r["nm"], r["tid"],
                     team["name"] if team else None, team["logo"] if team else None, r["val"]))
        out[category] = len(rows)
    db.mark_sync(f"players_calc:{league_id}", ok=True, note=str(out))
    return out


def recompute_all(only_league: int | None = None) -> dict:
    """Полный пересчёт. Дешёвая локальная операция, запросов к API не тратит."""
    result = {}
    for lid in ([only_league] if only_league else LEAGUE_IDS):
        result[lid] = {
            "league": LEAGUE_BY_ID[lid]["name_ru"],
            "standings": None if lid in FD_COMPETITIONS else compute_standings(lid),
            "players": compute_player_stats(lid),
        }
    return result


def coverage(league_id: int) -> dict:
    """Насколько полно собрана история лиги — показываем на сайте честно."""
    season = SEASON_BY_LEAGUE.get(league_id)
    total = db.query_one(
        f"""SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND season=?
            AND status_short IN ({','.join('?' * len(RESULT_STATUSES))})""",
        (league_id, season, *RESULT_STATUSES))["n"]
    detailed = db.query_one(
        """SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND season=? AND detail_synced_at>0""",
        (league_id, season))["n"]
    return {"finished": total, "with_details": detailed}
