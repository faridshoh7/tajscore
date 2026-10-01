"""Коэффициенты букмекера FORMULA55 на исход матча (1 / X / 2).

Третий источник данных, не связанный с двумя футбольными API и их лимитов не
тратящий. Сайт букмекера написан на Next.js и отдаёт данные прямо в разметке
страницы — внутри блоков `self.__next_f.push([1,"…"])` лежит экранированный
JSON. Браузер поэтому не нужен, хватает обычного HTTP.

Путь до цифр:
  1. /prematches/football                     — список всех турниров (id + slug)
  2. /prematches/football/{slug}-{champId}    — матчи одного турнира с коэффициентами
  3. /prematch/{slug}-{eventId}               — страница матча, туда ведут кнопки

Намеренно НЕ используются серверные действия Next.js (POST с заголовком
next-action): их идентификаторы меняются при каждом выкате сайта, и парсер
ломался бы каждые пару недель. Адреса страниц стабильны.

Сопоставление с нашими матчами идёт по дате и русским названиям команд: у
букмекера они тоже по-русски, а русские названия у нас уже есть (app/names.py).
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from app import db, teams_tj
from app.config import ODDS, SEASON_BY_LEAGUE

log = logging.getLogger("tajscore.odds")

BASE = "https://formula55.tj"
LIST_URL = f"{BASE}/prematches/football"
SIGNUP_URL = f"{BASE}/sign-up"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Ключи исходов в mainlines: 1_1 — победа хозяев, 1_2 — ничья, 1_3 — победа гостей
K_HOME, K_DRAW, K_AWAY = "1_1", "1_2", "1_3"

# Наш id лиги -> начало названия турнира у букмекера.
# Сравнение по началу строки: у них к названию добавляется стадия
# («Лига чемпионов УЕФА. Общий этап»), и она нам безразлична.
LEAGUE_CHAMPS = {
    571: ("Таджикистан.",),
    2:   ("Лига чемпионов УЕФА",),
    39:  ("Англия. Премьер-лига",),
    140: ("Испания. Примера Дивизион",),
    135: ("Италия. Серия A",),
    78:  ("Германия. Бундеслига",),
    61:  ("Франция. Лига 1",),
    3:   ("Лига Европы УЕФА",),
    848: ("Лига конференций УЕФА",),
    235: ("Россия. Премьер-лига", "Россия. Премьер-Лига"),
    307: ("Саудовская Аравия. Про",),
    253: ("США. MLS",),
    1:   ("Чемпионат мира",),
    5:   ("Лига наций УЕФА",),
    4:   ("Чемпионат Европы 20", "Чемпионат Европы."),
}

# Турниры, которые надо отбросить. Первая группа — это вообще не матчи, а ставки
# на исход сезона («кто станет чемпионом»). Вторая — чужие соревнования, которые
# иначе прилипают к мужским: женская Бундеслига к обычной, молодёжные к основным.
JUNK_PARTS = ("итоги", "статистик", "лучший", "лучшая", "кто выше", "победитель",
              "кто забьет", "кто забьёт", "какая команда", "кол-во голов",
              "команда из какой", "специальн")
EXCLUDE_PARTS = ("женщин", "жен.", "до 21", "до 19", "до 23", "u21", "u19", "u23",
                 "молодёж", "молодеж", "резерв", "дубл")


def _is_real_champ(title: str) -> bool:
    t = title.lower()
    return not any(p in t for p in JUNK_PARTS) and not any(p in t for p in EXCLUDE_PARTS)


# ------------------------------------------------------------------ загрузка
def _decode_blob(html: str) -> str:
    """Склеивает данные страницы из чанков self.__next_f.push([1,"…"])."""
    out = []
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html):
        try:
            out.append(json.loads('"' + chunk + '"'))
        except Exception:
            continue
    return "".join(out)


def _objects(blob: str, head: str) -> list[dict]:
    """Вытаскивает JSON-объекты, начинающиеся с head, считая баланс скобок.

    Регулярным выражением такое не берётся: внутри вложенные объекты.
    """
    out, seen = [], set()
    for m in re.finditer(re.escape(head), blob):
        i = m.start()
        depth, j, n = 0, i, len(blob)
        while j < n:
            c = blob[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
            if depth == 0:
                break
        else:
            continue
        try:
            obj = json.loads(blob[i:j])
        except Exception:
            continue
        if obj.get("id") not in seen:
            seen.add(obj.get("id"))
            out.append(obj)
    return out


class Fetcher:
    """HTTP-клиент с паузой между запросами: сайт чужой, частить незачем."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": UA, "Accept-Language": "ru,ru-RU;q=0.9"},
                timeout=ODDS["timeout"], follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def page(self, url: str) -> str | None:
        gap = ODDS["request_gap"] - (time.monotonic() - self._last)
        if gap > 0:
            await asyncio.sleep(gap)
        self._last = time.monotonic()
        try:
            r = await (await self._get_client()).get(url)
        except Exception as e:
            log.warning("сеть %s: %s", url, e)
            return None
        if r.status_code != 200:
            log.warning("%s -> HTTP %s", url, r.status_code)
            return None
        return r.text


fetcher = Fetcher()


# ------------------------------------------------------------------ разбор
async def champs() -> list[dict]:
    """Список турниров букмекера: [{id, title, slug, count}]."""
    html = await fetcher.page(LIST_URL)
    if not html:
        return []
    blob = _decode_blob(html)
    rows = re.findall(
        r'\{"id":(\d{3,7}),"count":(\d+),"title":"((?:[^"\\]|\\.)*)","position":\d+,"slug":"([^"]+)"\}',
        blob)
    out = []
    for cid, cnt, title, slug in rows:
        try:
            title = json.loads('"' + title + '"')
        except Exception:
            pass
        out.append({"id": int(cid), "count": int(cnt), "title": title, "slug": slug})
    return out


async def events(champ: dict) -> list[dict]:
    """Матчи одного турнира вместе с коэффициентами."""
    html = await fetcher.page(f"{LIST_URL}/{champ['slug']}-{champ['id']}")
    if not html:
        return []
    return _objects(_decode_blob(html), '{"id":')


def _price(raw) -> float | None:
    """«1.12» -> 1.12. Ноль и мусор отбрасываем: это не коэффициент."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if 1.0 < v < 1000 else None


def outcomes(ev: dict) -> tuple[float | None, float | None, float | None]:
    ml = ev.get("mainlines") or ev.get("additional") or {}
    return _price(ml.get(K_HOME)), _price(ml.get(K_DRAW)), _price(ml.get(K_AWAY))


def event_url(ev: dict) -> str:
    slug = (ev.get("slug") or {}).get("event") or ""
    return f"{BASE}/prematch/{slug}-{ev['id']}" if slug else SIGNUP_URL


# ------------------------------------------------------------------ сопоставление
def _key(name: str) -> str:
    """Название команды в сравнимый вид: без регистра, диакритики и пробелов."""
    return re.sub(r"[^а-яёa-z0-9]", "", teams_tj._fold(name or ""))


def _our_fixtures(league_id: int) -> list[dict]:
    """Наши матчи лиги, которые ещё не начались и стартуют в окне показа."""
    now = int(time.time())
    rows = db.query(
        """SELECT f.id, f.timestamp, f.home_id, f.away_id,
                  th.name home_name, ta.name away_name
           FROM fixtures f
           JOIN teams th ON th.id = f.home_id
           JOIN teams ta ON ta.id = f.away_id
           WHERE f.league_id = ? AND f.timestamp BETWEEN ? AND ?
             AND f.status_short IN ('NS','TBD','PST')""",
        (league_id, now, now + ODDS["window_ahead"]))
    out = []
    for r in rows:
        hru, _, _ = teams_tj.names(r["home_id"], r["home_name"])
        aru, _, _ = teams_tj.names(r["away_id"], r["away_name"])
        out.append({"id": r["id"], "ts": r["timestamp"],
                    "home": _key(hru), "away": _key(aru)})
    return out


def _match(ev: dict, ours: list[dict]) -> dict | None:
    """Ищет наш матч под событие букмекера: та же пара команд в тот же день.

    Допуск по времени большой: источники иногда расходятся на час-другой из-за
    переносов, а двух одинаковых пар в один день не бывает.
    """
    eh, ea = _key(ev.get("host")), _key(ev.get("guest"))
    if not eh or not ea:
        return None
    ets = ev.get("date") or 0
    for f in ours:
        if abs(f["ts"] - ets) > ODDS["time_tolerance"]:
            continue
        if (eh == f["home"] and ea == f["away"]) or (eh in f["home"] or f["home"] in eh) \
                and (ea in f["away"] or f["away"] in ea):
            return f
    return None


# ------------------------------------------------------------------ запись
def save(fixture_id: int, ev: dict, h, d, a) -> None:
    db.execute(
        """INSERT INTO odds (fixture_id, home, draw, away, event_id, url, updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(fixture_id) DO UPDATE SET
               home=excluded.home, draw=excluded.draw, away=excluded.away,
               event_id=excluded.event_id, url=excluded.url,
               updated_at=excluded.updated_at""",
        (fixture_id, h, d, a, ev["id"], event_url(ev), int(time.time())))


def cleanup() -> int:
    """Убирает коэффициенты начавшихся матчей: во время игры мы их не показываем."""
    cur = db.execute(
        """DELETE FROM odds WHERE fixture_id IN (
               SELECT o.fixture_id FROM odds o JOIN fixtures f ON f.id = o.fixture_id
               WHERE f.timestamp <= ?)""", (int(time.time()),))
    return cur.rowcount if cur else 0


def get(fixture_id: int) -> dict | None:
    """Коэффициенты для страницы матча. Протухшие не отдаём."""
    row = db.query_one("SELECT * FROM odds WHERE fixture_id=?", (fixture_id,))
    if not row:
        return None
    if int(time.time()) - row["updated_at"] > ODDS["max_age"]:
        return None
    return {"home": row["home"], "draw": row["draw"], "away": row["away"],
            "url": row["url"] or SIGNUP_URL, "updated_at": row["updated_at"]}


# ------------------------------------------------------------------ главный проход
async def sync() -> dict:
    """Обходит турниры, у которых есть наши ближайшие матчи, и пишет коэффициенты."""
    wanted = {lid: _our_fixtures(lid) for lid in LEAGUE_CHAMPS}
    wanted = {lid: fx for lid, fx in wanted.items() if fx}
    if not wanted:
        log.info("ближайших матчей нет — коэффициенты не нужны")
        return {"champs": 0, "saved": 0}

    all_champs = [c for c in await champs() if _is_real_champ(c["title"])]
    if not all_champs:
        log.warning("не удалось получить список турниров")
        return {"champs": 0, "saved": 0}

    saved = total_champs = 0
    for lid, ours in wanted.items():
        prefixes = LEAGUE_CHAMPS[lid]
        mine = [c for c in all_champs if any(c["title"].startswith(p) for p in prefixes)]
        for champ in mine:
            total_champs += 1
            for ev in await events(champ):
                f = _match(ev, ours)
                if not f:
                    continue
                h, d, a = outcomes(ev)
                if h is None and d is None and a is None:
                    continue
                save(f["id"], ev, h, d, a)
                saved += 1
    removed = cleanup()
    db.mark_sync("odds", ok=True, note=f"{saved} матчей, турниров {total_champs}")
    log.info("Коэффициенты: записано %s, турниров обойдено %s, убрано начавшихся %s",
             saved, total_champs, removed)
    return {"champs": total_champs, "saved": saved, "removed": removed}
