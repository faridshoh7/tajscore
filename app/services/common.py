"""Общие помощники выборок: время, статусы, сериализация матчей."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app import teams_tj
from app.config import DEFAULT_TZ, LEAGUE_BY_ID, TABLE_ZONES

LIVE_STATUSES = ("1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE")
FINISHED_STATUSES = ("FT", "AET", "PEN")
CANCELLED_STATUSES = ("PST", "CANC", "ABD", "AWD", "WO", "TBD")

# Человеческие подписи статусов (ключи для фронтового словаря переводов)
STATUS_KEY = {
    "TBD": "status.tbd", "NS": "status.ns", "1H": "status.first_half", "HT": "status.ht",
    "2H": "status.second_half", "ET": "status.et", "BT": "status.bt", "P": "status.pen_shootout",
    "SUSP": "status.susp", "INT": "status.int", "FT": "status.ft", "AET": "status.aet",
    "PEN": "status.pen", "PST": "status.pst", "CANC": "status.canc", "ABD": "status.abd",
    "AWD": "status.awd", "WO": "status.wo", "LIVE": "status.live",
}


def tzinfo(tz: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz or DEFAULT_TZ)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def day_range(date_str: str | None, tz: str | None, offset_days: int = 0) -> tuple[int, int]:
    """Границы локальных суток в unix-времени."""
    z = tzinfo(tz)
    if date_str:
        base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=z)
    else:
        base = datetime.now(z).replace(hour=0, minute=0, second=0, microsecond=0)
    start = base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def phase(status: str | None) -> str:
    if status in LIVE_STATUSES:
        return "live"
    if status in FINISHED_STATUSES:
        return "finished"
    if status in CANCELLED_STATUSES:
        return "cancelled"
    return "scheduled"


def fixture_row(r) -> dict:
    """Строка fixtures + join'ы -> словарь для фронта."""
    st = r["status_short"]
    return {
        "id": r["id"],
        "league_id": r["league_id"],
        "round": r["round"],
        "timestamp": r["timestamp"],
        "date_utc": r["date_utc"],
        "status": st,
        "status_key": STATUS_KEY.get(st, "status.ns"),
        "phase": phase(st),
        "elapsed": r["elapsed"],
        "extra_minute": r["extra_minute"] if "extra_minute" in r.keys() else None,
        # team_out подставляет русское и таджикское написание клубов Лигаи Олӣ
        # и локальную эмблему, если она загружена (см. app/teams_tj.py)
        "home": teams_tj.team_out(r["home_id"], r["home_name"], r["home_logo"]),
        "away": teams_tj.team_out(r["away_id"], r["away_name"], r["away_logo"]),
        "goals": {"home": r["home_goals"], "away": r["away_goals"]},
        "ht": {"home": r["ht_home"], "away": r["ht_away"]},
        "pen": {"home": r["pen_home"], "away": r["pen_away"]},
        "winner": r["winner"],
        "venue": r["venue_name"] if "venue_name" in r.keys() else None,
        # когда счёт последний раз обновлялся: на бесплатных тарифах у части лиг
        # он приходит с задержкой, и фронт честно показывает, насколько он свежий
        "updated_at": r["updated_at"] if "updated_at" in r.keys() else None,
    }


FIXTURE_SELECT = """
    SELECT f.*, th.name home_name, th.logo home_logo, ta.name away_name, ta.logo away_logo
    FROM fixtures f
    LEFT JOIN teams th ON th.id = f.home_id
    LEFT JOIN teams ta ON ta.id = f.away_id
"""


def league_info(league_id: int) -> dict | None:
    r = db.query_one("SELECT * FROM leagues WHERE id=?", (league_id,))
    if not r:
        return None
    cfg = LEAGUE_BY_ID.get(league_id, {})
    return {
        "id": r["id"], "name": r["name_ru"], "name_ru": r["name_ru"], "name_tg": r["name_tg"],
        "name_en": r["name"], "country": r["country_ru"], "country_ru": r["country_ru"],
        "country_tg": r["country_tg"], "country_en": cfg.get("country_en") or r["country"],
        "logo": r["logo"], "flag": r["flag"],
        "season": r["season"], "is_cup": bool(r["is_cup"]), "group_stage": bool(r["group_stage"]),
        "priority": r["priority"], "code": r["code"],
        "zones": TABLE_ZONES.get(league_id, {}),
    }


def group_by_league(rows: list[dict]) -> list[dict]:
    """Матчи -> список лиг с матчами, в порядке приоритета лиги."""
    buckets: dict[int, list] = {}
    for m in rows:
        buckets.setdefault(m["league_id"], []).append(m)
    out = []
    for lid, items in buckets.items():
        info = league_info(lid)
        if not info:
            continue
        items.sort(key=lambda x: (x["timestamp"], x["id"]))
        out.append({"league": info, "matches": items})
    out.sort(key=lambda g: g["league"]["priority"])
    return out
