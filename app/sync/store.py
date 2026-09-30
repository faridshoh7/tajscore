"""Разбор ответов API-Football и запись в SQLite."""
import json
import time

from app import db
from app.config import LEAGUE_BY_ID


def _team(conn, t: dict) -> int | None:
    """Команды приезжают внутри матчей — отдельных запросов на них не тратим."""
    if not t or not t.get("id"):
        return None
    conn.execute(
        """INSERT INTO teams (id, name, logo) VALUES (?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, logo=excluded.logo""",
        (t["id"], t.get("name"), t.get("logo")),
    )
    return t["id"]


def save_fixtures(items: list[dict], only_known_leagues: bool = True) -> int:
    """Сохраняет список матчей. Возвращает число записанных."""
    now = int(time.time())
    n = 0
    with db.write() as conn:
        for it in items:
            fx, lg = it.get("fixture") or {}, it.get("league") or {}
            if not fx.get("id"):
                continue
            if only_known_leagues and lg.get("id") not in LEAGUE_BY_ID:
                continue
            teams, goals, score = it.get("teams") or {}, it.get("goals") or {}, it.get("score") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            hid, aid = _team(conn, home), _team(conn, away)
            st = fx.get("status") or {}
            venue = fx.get("venue") or {}
            ht, ftm = score.get("halftime") or {}, score.get("fulltime") or {}
            et, pen = score.get("extratime") or {}, score.get("penalty") or {}
            winner = "home" if home.get("winner") else ("away" if away.get("winner") else
                     ("draw" if home.get("winner") is False and away.get("winner") is False else None))
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
                (fx["id"], lg.get("id"), lg.get("season"), lg.get("round"), fx.get("date"),
                 fx.get("timestamp"), st.get("short"), st.get("long"), st.get("elapsed"),
                 st.get("extra"), venue.get("name"), venue.get("city"), fx.get("referee"),
                 hid, aid, goals.get("home"), goals.get("away"),
                 ht.get("home"), ht.get("away"), ftm.get("home"), ftm.get("away"),
                 et.get("home"), et.get("away"), pen.get("home"), pen.get("away"), winner, now),
            )
            n += 1
    return n


def save_events(fixture_id: int, events: list[dict]) -> int:
    with db.write() as conn:
        conn.execute("DELETE FROM fixture_events WHERE fixture_id=?", (fixture_id,))
        rows = []
        for i, e in enumerate(events or []):
            t, team = e.get("time") or {}, e.get("team") or {}
            pl, asst = e.get("player") or {}, e.get("assist") or {}
            _team(conn, team)
            rows.append((fixture_id, i, t.get("elapsed"), t.get("extra"), team.get("id"),
                         pl.get("id"), pl.get("name"), asst.get("id"), asst.get("name"),
                         e.get("type"), e.get("detail"), e.get("comments")))
        conn.executemany(
            """INSERT INTO fixture_events (fixture_id, idx, minute, extra, team_id, player_id,
                   player_name, assist_id, assist_name, type, detail, comments)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    return len(rows)


def save_statistics(fixture_id: int, stats: list[dict]) -> int:
    n = 0
    with db.write() as conn:
        conn.execute("DELETE FROM fixture_stats WHERE fixture_id=?", (fixture_id,))
        for block in stats or []:
            tid = _team(conn, block.get("team") or {})
            for s in block.get("statistics") or []:
                val = s.get("value")
                conn.execute(
                    "INSERT OR REPLACE INTO fixture_stats (fixture_id, team_id, stat_key, value) VALUES (?,?,?,?)",
                    (fixture_id, tid, s.get("type"), None if val is None else str(val)))
                n += 1
    return n


def save_lineups(fixture_id: int, lineups: list[dict]) -> int:
    n = 0
    with db.write() as conn:
        conn.execute("DELETE FROM fixture_lineups WHERE fixture_id=?", (fixture_id,))
        conn.execute("DELETE FROM fixture_players WHERE fixture_id=?", (fixture_id,))
        for lu in lineups or []:
            tid = _team(conn, lu.get("team") or {})
            coach = lu.get("coach") or {}
            conn.execute(
                "INSERT OR REPLACE INTO fixture_lineups (fixture_id, team_id, formation, coach_name, coach_photo) VALUES (?,?,?,?,?)",
                (fixture_id, tid, lu.get("formation"), coach.get("name"), coach.get("photo")))
            for group, is_start in (("startXI", 1), ("substitutes", 0)):
                for item in lu.get(group) or []:
                    p = item.get("player") or {}
                    if not p.get("id"):
                        continue
                    conn.execute(
                        """INSERT OR REPLACE INTO fixture_players
                           (fixture_id, team_id, player_id, name, number, pos, grid, is_start)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (fixture_id, tid, p["id"], p.get("name"), p.get("number"),
                         p.get("pos"), p.get("grid"), is_start))
                    n += 1
    return n


def mark_detail_synced(fixture_id: int) -> None:
    db.execute("UPDATE fixtures SET detail_synced_at=? WHERE id=?", (int(time.time()), fixture_id))


def save_standings(league_id: int, season: int, payload: list[dict]) -> int:
    """payload = ответ /standings. Внутри может быть несколько групп (кубки)."""
    if not payload:
        return 0
    now, n = int(time.time()), 0
    groups = ((payload[0].get("league") or {}).get("standings")) or []
    with db.write() as conn:
        conn.execute("DELETE FROM standings WHERE league_id=? AND season=?", (league_id, season))
        for grp in groups:
            for row in grp:
                team = row.get("team") or {}
                tid = _team(conn, team)
                allst = row.get("all") or {}
                g = allst.get("goals") or {}
                conn.execute(
                    """INSERT OR REPLACE INTO standings (league_id, season, group_name, team_id, rank,
                          played, win, draw, lose, gf, ga, gd, points, form, description,
                          home_json, away_json, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (league_id, season, row.get("group") or "", tid, row.get("rank"),
                     allst.get("played"), allst.get("win"), allst.get("draw"), allst.get("lose"),
                     g.get("for"), g.get("against"), row.get("goalsDiff"), row.get("points"),
                     row.get("form"), row.get("description"),
                     json.dumps(row.get("home") or {}), json.dumps(row.get("away") or {}), now))
                n += 1
    return n


CATEGORY_FIELD = {
    "goals":   lambda s: (s.get("goals") or {}).get("total"),
    "assists": lambda s: (s.get("goals") or {}).get("assists"),
    "yellow":  lambda s: (s.get("cards") or {}).get("yellow"),
    "red":     lambda s: (s.get("cards") or {}).get("red"),
}


def save_player_stats(league_id: int, season: int, category: str, payload: list[dict]) -> int:
    getter = CATEGORY_FIELD[category]
    with db.write() as conn:
        conn.execute("DELETE FROM player_stats WHERE league_id=? AND season=? AND category=?",
                     (league_id, season, category))
        rank = 0
        for item in payload or []:
            p = item.get("player") or {}
            st = next((s for s in (item.get("statistics") or [])
                       if (s.get("league") or {}).get("id") == league_id), None) \
                 or (item.get("statistics") or [{}])[0]
            value = getter(st) or 0
            team = st.get("team") or {}
            games = st.get("games") or {}
            _team(conn, team)
            rank += 1
            conn.execute(
                """INSERT OR REPLACE INTO player_stats (league_id, season, category, rank, player_id,
                      name, photo, team_id, team_name, team_logo, value, games, minutes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (league_id, season, category, rank, p.get("id"), p.get("name"), p.get("photo"),
                 team.get("id"), team.get("name"), team.get("logo"), value,
                 games.get("appearences"), games.get("minutes")))
    return rank
