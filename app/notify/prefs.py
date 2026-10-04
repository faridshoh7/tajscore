"""Настройки уведомлений пользователя.

Хранятся одним JSON-объектом в notify_prefs. Всё, что приходит из браузера,
проходит через clean(): неизвестные ключи выбрасываются, значения приводятся
к допустимым. Поэтому в базе всегда лежит полный и корректный объект.

Главный выключатель — users.notifications_enabled (он был и раньше, его же
переключает бот командой /stop). Здесь — тонкая настройка поверх него.
"""
import copy
import json
import re
import time
from zoneinfo import ZoneInfo

from app import db

# События, о которых можно уведомлять
EVENTS = ("reminder", "lineups", "kickoff", "goal", "goal_cancelled", "red_card",
          "halftime", "fulltime", "postponed")

# «Ключевые» события — то, что приходит по лигам в режиме «key»: начало, итог,
# перенос. Голы всех матчей лиги — это десятки сообщений за вечер, поэтому
# по умолчанию лига присылает только ключевое.
KEY_EVENTS = ("reminder", "kickoff", "fulltime", "postponed")

LEVELS = ("all", "key", "off")
REMINDER_OPTIONS = (5, 15, 30, 60, 120)
LANGS = ("ru", "tg", "en")

DEFAULTS = {
    "lang": "ru",
    "tz": "Asia/Dushanbe",
    "channels": {"telegram": True, "push": True},
    "events": {
        "reminder": True, "lineups": False, "kickoff": True, "goal": True,
        "goal_cancelled": True, "red_card": True, "halftime": False,
        "fulltime": True, "postponed": True,
    },
    "reminder_min": 15,
    # Насколько подробно уведомлять по каждому виду избранного
    "sources": {"teams": "all", "matches": "all", "leagues": "key"},
    # Тихие часы: silent — присылать без звука, skip — не присылать совсем
    "quiet": {"enabled": False, "from": "23:00", "to": "08:00", "mode": "silent"},
}

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def clean(raw) -> dict:
    """Приводит произвольный объект к корректным настройкам."""
    out = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    if raw.get("lang") in LANGS:
        out["lang"] = raw["lang"]
    tz = raw.get("tz")
    if isinstance(tz, str) and len(tz) < 64:
        try:
            ZoneInfo(tz)
            out["tz"] = tz
        except Exception:
            pass
    ch = raw.get("channels")
    if isinstance(ch, dict):
        for k in out["channels"]:
            if isinstance(ch.get(k), bool):
                out["channels"][k] = ch[k]
    ev = raw.get("events")
    if isinstance(ev, dict):
        for k in EVENTS:
            if isinstance(ev.get(k), bool):
                out["events"][k] = ev[k]
    try:
        rm = int(raw.get("reminder_min", out["reminder_min"]))
        if rm in REMINDER_OPTIONS:
            out["reminder_min"] = rm
    except (TypeError, ValueError):
        pass
    src = raw.get("sources")
    if isinstance(src, dict):
        for k in out["sources"]:
            if src.get(k) in LEVELS:
                out["sources"][k] = src[k]
    q = raw.get("quiet")
    if isinstance(q, dict):
        if isinstance(q.get("enabled"), bool):
            out["quiet"]["enabled"] = q["enabled"]
        for k in ("from", "to"):
            if isinstance(q.get(k), str) and _TIME.match(q[k]):
                out["quiet"][k] = q[k]
        if q.get("mode") in ("silent", "skip"):
            out["quiet"]["mode"] = q["mode"]
    return out


def merge(base: dict, patch) -> dict:
    """Частичное обновление: в patch можно прислать только изменившиеся поля."""
    if not isinstance(patch, dict):
        return clean(base)
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return clean(out)


def load(user_id: int) -> dict:
    row = db.query_one("SELECT prefs FROM notify_prefs WHERE user_id=?", (user_id,))
    if not row:
        return copy.deepcopy(DEFAULTS)
    try:
        return clean(json.loads(row["prefs"]))
    except Exception:
        return copy.deepcopy(DEFAULTS)


def load_many(user_ids) -> dict[int, dict]:
    ids = list(set(user_ids))
    out = {uid: copy.deepcopy(DEFAULTS) for uid in ids}
    if not ids:
        return out
    rows = db.query(
        f"SELECT user_id, prefs FROM notify_prefs WHERE user_id IN ({','.join('?' * len(ids))})",
        tuple(ids))
    for r in rows:
        try:
            out[r["user_id"]] = clean(json.loads(r["prefs"]))
        except Exception:
            pass
    return out


def save(user_id: int, prefs: dict) -> dict:
    prefs = clean(prefs)
    db.execute(
        """INSERT INTO notify_prefs (user_id, prefs, updated_at) VALUES (?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET prefs=excluded.prefs, updated_at=excluded.updated_at""",
        (user_id, json.dumps(prefs, ensure_ascii=False), int(time.time())))
    return prefs


def level_allows(level: str, event: str) -> bool:
    if level == "all":
        return True
    if level == "key":
        return event in KEY_EVENTS
    return False


def in_quiet_hours(prefs: dict, now: float | None = None) -> bool:
    q = prefs.get("quiet") or {}
    if not q.get("enabled"):
        return False
    try:
        from datetime import datetime
        local = datetime.fromtimestamp(now or time.time(), ZoneInfo(prefs.get("tz") or "Asia/Dushanbe"))
    except Exception:
        return False
    cur = local.hour * 60 + local.minute
    fh, fm = map(int, q["from"].split(":"))
    th, tm = map(int, q["to"].split(":"))
    start, end = fh * 60 + fm, th * 60 + tm
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end      # интервал через полночь: 23:00–08:00


# ------------------------------------------------------------------ «не беспокоить по матчу»
def set_mute(user_id: int, fixture_id: int, muted: bool) -> None:
    if muted:
        db.execute("INSERT OR IGNORE INTO notify_mutes (user_id, fixture_id, created_at) VALUES (?,?,?)",
                   (user_id, fixture_id, int(time.time())))
    else:
        db.execute("DELETE FROM notify_mutes WHERE user_id=? AND fixture_id=?", (user_id, fixture_id))


def is_muted(user_id: int, fixture_id: int) -> bool:
    return bool(db.query_one("SELECT 1 FROM notify_mutes WHERE user_id=? AND fixture_id=?",
                             (user_id, fixture_id)))
