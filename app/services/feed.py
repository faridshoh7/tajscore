"""Лента матчей для главной страницы."""
from app import db
from app.config import LEAGUE_IDS, POPULAR_LEAGUE_IDS
from app.services.common import (FINISHED_STATUSES, FIXTURE_SELECT, LIVE_STATUSES,
                                 day_range, fixture_row, group_by_league)

_IN_LEAGUES = ",".join("?" * len(LEAGUE_IDS))


def _rows(where: str, params: tuple) -> list[dict]:
    sql = f"{FIXTURE_SELECT} WHERE f.league_id IN ({_IN_LEAGUES}) AND {where} ORDER BY f.timestamp"
    return [fixture_row(r) for r in db.query(sql, (*LEAGUE_IDS, *params))]


def live_matches() -> list[dict]:
    q = ",".join("?" * len(LIVE_STATUSES))
    return _rows(f"f.status_short IN ({q})", LIVE_STATUSES)


def day_matches(date_str: str | None, tz: str | None, offset_days: int = 0) -> list[dict]:
    start, end = day_range(date_str, tz, offset_days)
    return _rows("f.timestamp >= ? AND f.timestamp < ?", (start, end))


def all_matches(tz: str | None) -> list[dict]:
    """«Все» — окно вчера..завтра, как у Flashscore: живые сверху."""
    start, _ = day_range(None, tz, -1)
    _, end = day_range(None, tz, 1)
    return _rows("f.timestamp >= ? AND f.timestamp < ?", (start, end))


def feed(tab: str = "today", tz: str | None = None, date_str: str | None = None) -> dict:
    tab = (tab or "today").lower()
    if tab == "live":
        matches = live_matches()
    elif tab == "yesterday":
        matches = day_matches(None, tz, -1)
    elif tab == "tomorrow":
        matches = day_matches(None, tz, 1)
    elif tab == "all":
        matches = all_matches(tz)
    elif tab == "date" and date_str:
        matches = day_matches(date_str, tz)
    else:
        tab = "today"
        matches = day_matches(None, tz)
    return {
        "tab": tab,
        "count": len(matches),
        "live_count": sum(1 for m in matches if m["phase"] == "live"),
        "groups": group_by_league(matches),
    }


def live_scores() -> dict:
    """Лёгкий ответ для автообновления: только счёт, минута и статус."""
    q = ",".join("?" * len(LIVE_STATUSES))
    rows = db.query(
        f"""SELECT id, status_short, elapsed, extra_minute, home_goals, away_goals, updated_at
            FROM fixtures WHERE league_id IN ({_IN_LEAGUES}) AND status_short IN ({q})""",
        (*LEAGUE_IDS, *LIVE_STATUSES))
    return {"matches": [
        {"id": r["id"], "status": r["status_short"], "elapsed": r["elapsed"],
         "extra_minute": r["extra_minute"], "home": r["home_goals"], "away": r["away_goals"],
         "updated_at": r["updated_at"]}
        for r in rows]}


def sidebar_leagues() -> list[dict]:
    """Левая колонка: лиги + сколько матчей сегодня и сколько живых."""
    from app.services.common import league_info
    start, end = day_range(None, None)
    out = []
    for lid in LEAGUE_IDS:
        info = league_info(lid)
        if not info:
            continue
        cnt = db.query_one(
            "SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND timestamp>=? AND timestamp<?",
            (lid, start, end))["n"]
        q = ",".join("?" * len(LIVE_STATUSES))
        live = db.query_one(
            f"SELECT COUNT(*) n FROM fixtures WHERE league_id=? AND status_short IN ({q})",
            (lid, *LIVE_STATUSES))["n"]
        info["today_count"], info["live_count"] = cnt, live
        out.append(info)
    return out


def popular() -> list[dict]:
    """Правая колонка: живые матчи, иначе ближайшие из топ-лиг."""
    live = live_matches()
    if live:
        return live[:8]
    q = ",".join("?" * len(POPULAR_LEAGUE_IDS))
    import time
    sql = (f"{FIXTURE_SELECT} WHERE f.league_id IN ({q}) AND f.timestamp > ? "
           f"ORDER BY f.timestamp LIMIT 8")
    return [fixture_row(r) for r in db.query(sql, (*POPULAR_LEAGUE_IDS, int(time.time()) - 7200))]


def brief(ids: list[int]) -> list[dict]:
    """Матчи по списку id в том же порядке, что и просили."""
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    rows = {r["id"]: fixture_row(r) for r in db.query(f"{FIXTURE_SELECT} WHERE f.id IN ({q})", tuple(ids))}
    return [rows[i] for i in ids if i in rows]
