"""Русские написания имён игроков — из Wikidata.

Зачем внешний источник. Оба API отдают имена латиницей, а транслитерация тут
не работает: чтение зависит от языка. Испанское «Julián» — это Хулиан, а не
Джулиан; «Haaland» по-русски пишут Холанн, а не Хааланд; «Suzuki» — Судзуки.
Правилами это не берётся, а справочник на сотни игроков, которые меняются
каждый тур, руками не прокормить.

Wikidata хранит подписи на всех языках, выложена под CC0 и отвечает именно
теми написаниями, которые приняты в русской спортивной прессе.

Найденное кладётся в таблицу person_names: один человек запрашивается ровно
один раз. Ненайденное тоже помечается — чтобы не долбить API на каждом показе
страницы.
"""
import asyncio
import logging
import re
import time

import httpx

from app import db
from app.names import to_tajik

log = logging.getLogger("tajscore.wikidata")

API = "https://www.wikidata.org/w/api.php"
# Википедия просит представляться: по User-Agent они связываются при проблемах.
UA = "Tajscore/1.0 (https://tajscore.duckdns.org; football scores site)"
GAP = 0.4          # пауза между запросами — вежливый темп для открытого API
TIMEOUT = 20.0

# Признаки футболиста в описании сущности. Нужны, чтобы «Marcus Rashford» не
# совпал с однофамильцем-музыкантом: по имени Wikidata находит кого угодно.
_FOOTBALL = ("футболист", "футболистка", "football", "footballer", "soccer")


def cached(latin: str) -> tuple[str, str] | None:
    """(русское, таджикское) из кэша. None — ещё не искали или не нашли."""
    manual = OVERRIDE.get(latin)
    if manual:
        return manual, to_tajik(manual)
    row = db.query_one("SELECT ru, tg FROM person_names WHERE latin=?", (latin,))
    if row and row["ru"]:
        return row["ru"], row["tg"] or to_tajik(row["ru"])
    return None


def is_checked(latin: str) -> bool:
    if latin in OVERRIDE:
        return True
    row = db.query_one("SELECT checked_at FROM person_names WHERE latin=?", (latin,))
    return bool(row and row["checked_at"])



# Ручные исключения: латинское имя из API -> как показывать по-русски.
#
# Нужны по двум причинам.
#   1. Игровое имя вместо паспортного. Бразильцы и испанцы часто выступают под
#      прозвищем, а Wikidata хранит полное имя: «Raphinha» там «Рафаэль Диас
#      Беллоли». Общего правила нет — у одних лишнее слово в середине, у других
#      в конце, — поэтому только вручную.
#   2. Спорное написание. «Haaland» по-норвежски звучит как Холанн (конечная d
#      не читается), так пишут Википедия и часть прессы, но привычнее Холанд.
#      Здесь выбор за владельцем сайта, а не за источником.
#
# Исключение сильнее Wikidata: если имя есть здесь, в сеть за ним не ходим.
OVERRIDE = {
    # игровые имена
    "Raphinha": "Рафинья",
    "Vitinha": "Витинья",
    "Luiz Henrique": "Луис Энрике",
    "Luis Suárez": "Луис Суарес",
    "Roberto Fernández": "Роберто Фернандес",
    "Gerard Moreno": "Жерар Морено",
    "Ander Barrenetxea": "Андер Барренечеа",
    "Cucho Hernández": "Кучо Эрнандес",
    "Luis Díaz": "Луис Диас",
    "Mbwana Samatta": "Мбвана Саматта",
    "Hákon Haraldsson": "Хаукон Харальдссон",
    "Daniel Muñoz": "Даниэль Муньос",
    "Nicolae Stanciu": "Николае Станчу",
    "Julio Enciso": "Хулио Энсисо",
    "Pau Cubarsí": "Пау Кубарси",
    "Samu Costa": "Саму Кошта",
    "Guilherme Biro": "Гильерме Биро",
    # спорное написание — решение владельца сайта
    "Erling Haaland": "Эрлинг Холанд",
}


# Окончания отчеств. Нужны, чтобы отличить «Владимирович» от части фамилии
# вроде «Ван» в «Бранко Ван ден Бомен».
_PATRONYMIC = re.compile(r"(ович|евич|ьевич|овна|евна|ична|инична)$", re.I)


def clean_label(ru: str | None) -> str | None:
    """Снимает уточнение в скобках.

    У тёзок Wikidata различает статьи прямо в подписи: «Жуан Педро (футболист,
    2001)». В таблице бомбардиров это выглядит как ошибка вёрстки, а нужна
    только сама фамилия.
    """
    if not ru:
        return None
    ru = re.sub(r"\s*\([^)]*\)", "", ru).strip()
    # Часть подписей идёт в каталожном порядке: «Сьерра, Мигель». На странице
    # нужен обычный «Мигель Сьерра», поэтому разворачиваем.
    if ru.count(",") == 1:
        last, first = (p.strip() for p in ru.split(","))
        if last and first:
            ru = f"{first} {last}"
    # У русских и украинских игроков в подписи стоит отчество
    # («Николай Владимирович Шапаренко»). На табло оно не нужно.
    parts = ru.split()
    if len(parts) == 3 and _PATRONYMIC.search(parts[1]):
        ru = f"{parts[0]} {parts[2]}"
    return ru or None


def _store(latin: str, ru: str | None, qid: str | None) -> None:
    ru = clean_label(ru)
    db.execute(
        """INSERT INTO person_names (latin, ru, tg, qid, checked_at) VALUES (?,?,?,?,?)
           ON CONFLICT(latin) DO UPDATE SET
               ru=excluded.ru, tg=excluded.tg, qid=excluded.qid,
               checked_at=excluded.checked_at""",
        (latin, ru, to_tajik(ru) if ru else None, qid, int(time.time())))


def _pick(results: list[dict]) -> dict | None:
    """Из найденного берём того, кто действительно футболист."""
    for r in results:
        desc = (r.get("description") or "").lower()
        if any(k in desc for k in _FOOTBALL):
            return r
    return None


async def resolve(client: httpx.AsyncClient, latin: str) -> str | None:
    """Ищет русскую подпись. Возвращает её либо None, если не нашлось."""
    try:
        r = await client.get(API, params={
            "action": "wbsearchentities",
            "search": latin,
            "language": "en",
            "uselang": "ru",     # подписи и описания придут по-русски
            "type": "item",
            "limit": 8,
            "format": "json",
        })
        data = r.json()
    except Exception as e:
        log.warning("Wikidata %r: %s", latin, e)
        return None

    hit = _pick(data.get("search") or [])
    if not hit:
        _store(latin, None, None)
        return None
    ru = hit.get("label")
    # Подпись на латинице означает, что русской у сущности нет — тогда толку нет
    if not ru or not any("Ѐ" <= c <= "ӿ" for c in ru):
        _store(latin, None, hit.get("id"))
        return None
    _store(latin, ru, hit.get("id"))
    return clean_label(ru)


async def resolve_many(names: list[str], limit: int | None = None) -> dict:
    """Догоняет написания для списка имён. Уже проверенные пропускает."""
    todo = [n for n in dict.fromkeys(names) if n and not is_checked(n)]
    if limit:
        todo = todo[:limit]
    found = 0
    if not todo:
        return {"checked": 0, "found": 0}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as client:
        for n in todo:
            if await resolve(client, n):
                found += 1
            await asyncio.sleep(GAP)
    log.info("Wikidata: проверено %s имён, найдено %s", len(todo), found)
    return {"checked": len(todo), "found": found}


# Все места, где в базе лежат имена людей. Держим одним списком, чтобы добор
# не пропустил таблицу: игроки приходят и в статистике, и в событиях, и в составах.
_NAME_SOURCES = (
    "SELECT name n FROM player_stats WHERE name IS NOT NULL",
    "SELECT player_name FROM fixture_events WHERE player_name IS NOT NULL",
    "SELECT assist_name FROM fixture_events WHERE assist_name IS NOT NULL",
    "SELECT name FROM fixture_players WHERE name IS NOT NULL",
)


def pending(limit: int = 40) -> list[str]:
    """Имена, которые ещё ни разу не искали. Порядок — от популярных к редким:
    сначала те, кто попал в таблицу бомбардиров, их чаще всего и видят."""
    rows = db.query(
        f"""SELECT n FROM ({' UNION '.join(_NAME_SOURCES)})
            WHERE n NOT IN (SELECT latin FROM person_names WHERE checked_at > 0)
            LIMIT ?""", (limit,))
    return [r["n"] for r in rows]


def localize(latin: str | None, lang: str = "ru") -> str:
    """Имя для показа. Нет перевода — отдаём латиницу, она честнее выдумки."""
    if not latin:
        return ""
    pair = cached(latin)
    if not pair:
        return latin
    return pair[1] if lang == "tg" else pair[0]
