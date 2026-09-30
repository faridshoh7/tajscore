"""Поиск по командам, лигам и матчам."""
from app import db
from app import teams_tj
from app.config import LEAGUE_IDS
from app.services.common import FIXTURE_SELECT, fixture_row, league_info


def _tj_ids(q: str) -> list[int]:
    """id клубов Лигаи Олӣ, подходящих под кириллический запрос.

    В таблице teams клуб хранится как «Istiqlol», поэтому запрос «Истиклол»
    обычным LIKE не находится. Прогоняем список команд через справочник и
    возвращаем id тех, чьё русское или таджикское имя совпало.
    """
    slugs = teams_tj.slugs_matching(q)
    if not slugs:
        return []
    return [r["id"] for r in db.query("SELECT id, name FROM teams")
            if teams_tj.slug_for(r["id"], r["name"]) in slugs]


def search(q: str, limit: int = 12) -> dict:
    q = (q or "").strip()
    if len(q) < 2:
        return {"leagues": [], "teams": [], "matches": []}
    like = f"%{q}%"
    tj_ids = _tj_ids(q)
    # плейсхолдеры для IN (...): при пустом списке подставляем заведомо
    # ложное условие, чтобы не городить две версии запроса
    tj_in = ",".join("?" * len(tj_ids)) if tj_ids else "NULL"
    leagues = [league_info(r["id"]) for r in db.query(
        "SELECT id FROM leagues WHERE name_ru LIKE ? OR name_tg LIKE ? OR name LIKE ? OR country_ru LIKE ? ORDER BY priority LIMIT ?",
        (like, like, like, like, limit))]
    teams = [teams_tj.team_out(r["id"], r["name"], r["logo"]) for r in db.query(
        f"""SELECT DISTINCT t.id, t.name, t.logo FROM teams t
           JOIN fixtures f ON (f.home_id=t.id OR f.away_id=t.id)
           WHERE t.name LIKE ? OR t.id IN ({tj_in}) ORDER BY t.name LIMIT ?""",
        (like, *tj_ids, limit))]
    ids = ",".join("?" * len(LEAGUE_IDS))
    matches = [fixture_row(r) for r in db.query(
        f"""{FIXTURE_SELECT} WHERE f.league_id IN ({ids})
            AND (th.name LIKE ? OR ta.name LIKE ?
                 OR f.home_id IN ({tj_in}) OR f.away_id IN ({tj_in}))
            ORDER BY ABS(f.timestamp - strftime('%s','now')) LIMIT ?""",
        (*LEAGUE_IDS, like, like, *tj_ids, *tj_ids, limit))]
    return {"leagues": leagues, "teams": teams, "matches": matches}


def team_page(team_id: int, limit: int = 30) -> dict | None:
    t = db.query_one("SELECT * FROM teams WHERE id=?", (team_id,))
    if not t:
        return None
    rows = db.query(
        f"{FIXTURE_SELECT} WHERE f.home_id=? OR f.away_id=? ORDER BY f.timestamp DESC LIMIT ?",
        (team_id, team_id, limit))
    team = dict(t)
    team.update(teams_tj.team_out(t["id"], t["name"], t["logo"]))
    # У клубов Лигаи Олӣ вместо страны показываем город — он говорит больше
    city_ru, city_tg = teams_tj.city(t["id"], t["name"])
    team["city_ru"], team["city_tg"] = city_ru, city_tg
    return {"team": team, "matches": [fixture_row(r) for r in rows]}
