"""Поиск по командам, лигам и матчам."""
from app import db
from app import teams_tj
from app.config import LEAGUE_IDS
from app.services.common import FIXTURE_SELECT, fixture_row, league_info


def _tj_ids(q: str) -> list[int]:
    """id команд, чьё русское или таджикское название подходит под запрос.

    В таблице teams команда хранится латиницей («Istiqlol», «Bayern München»),
    поэтому запрос «Истиклол» или «Бавария» обычным LIKE не находится.
    Прогоняем список через справочник имён и сверяем уже кириллицу.

    Сравнение идёт через _fold: он гасит разницу «Ҳосилот»/«Хосилот», так что
    таджикский запрос находит клуб с русским написанием и наоборот.
    """
    q = teams_tj._fold(q)
    if len(q) < 2:
        return []
    out = []
    for r in db.query("SELECT id, name FROM teams"):
        ru, tg, en = teams_tj.names(r["id"], r["name"])
        # Английский тоже ищем: латинский запрос «Bayern» должен находить Баварию
        if q in teams_tj._fold(ru) or q in teams_tj._fold(tg) or q in en.lower():
            out.append(r["id"])
    return out


def _teams(like: str, tj_ids: list[int], tj_in: str, q: str, limit: int) -> list[dict]:
    """Команды под запрос: без дублей и с совпадением по началу слова вверху.

    Один клуб приходит из двух источников под разными латинскими именами
    («Man City» и «Manchester City»), и в базе это две строки. Русское название
    у них одно, поэтому схлопываем по нему — иначе в подсказке будет две
    одинаковых строки. Из пары оставляем ту, у которой есть эмблема.
    """
    rows = db.query(
        f"""SELECT DISTINCT t.id, t.name, t.logo FROM teams t
           JOIN fixtures f ON (f.home_id=t.id OR f.away_id=t.id)
           WHERE t.name LIKE ? OR t.id IN ({tj_in})""",
        (like, *tj_ids))
    best: dict[str, dict] = {}
    for r in rows:
        out = teams_tj.team_out(r["id"], r["name"], r["logo"])
        prev = best.get(out["name"])
        if prev is None or (not prev.get("logo") and out.get("logo")):
            best[out["name"]] = out
    fq = teams_tj._fold(q)
    # «Реал» должен поднять Реал Мадрид выше Монреаля: сначала совпадения
    # с начала названия, потом всё остальное, внутри группы — по алфавиту
    return sorted(best.values(),
                  key=lambda t: (not teams_tj._fold(t["name"]).startswith(fq),
                                 t["name"]))[:limit]


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
    teams = _teams(like, tj_ids, tj_in, q, limit)
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
