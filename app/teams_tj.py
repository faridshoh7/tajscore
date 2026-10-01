"""Названия и эмблемы клубов Лигаи Олӣ.

Зачем это нужно. API-Football отдаёт таджикские клубы латиницей и в своём
написании: «Khosilot Farkhor», «CSKA Pomir», «Barki Tajik». Для сайта, у
которого две аудитории — русская и таджикская, — это нечитаемо. Поэтому
здесь лежит ручной справочник: каждому клубу сопоставлены русское и
таджикское написание, город и файл эмблемы.

Клуб находится двумя путями: по id команды в API (надёжно, id не меняется)
и по латинскому имени (страховка для тех клубов, чей id мы ещё не видели —
новичок лиги появится в базе сам, как только сыграет первый матч).

Эмблемы кладутся в static/logosligaioli/ под именем slug'а (см. README там же).
Если файла нет — остаётся логотип из API, страница не ломается.
"""
import re
import time

from app import names as app_names
from app.config import STATIC_DIR

LOGO_DIRNAME = "logosligaioli"
LOGO_DIR = STATIC_DIR / LOGO_DIRNAME
LOGO_EXTS = (".png", ".svg", ".webp", ".jpg", ".jpeg")

# slug -> описание клуба.
#   ids     — id команд в API-Football (у клуба их может быть несколько,
#             если API завёл дубль под другим написанием)
#   aliases — латинские написания на случай неизвестного id
#   ru / tg — как показываем название
#   city_*  — город, показываем отдельной строкой на странице команды
CLUBS = {
    "istiqlol": {
        "ids": [8012], "aliases": ["istiqlol", "istiklol", "fcistiqlol"],
        "ru": "Истиклол", "tg": "Истиқлол",
        "city_ru": "Душанбе", "city_tg": "Душанбе",
        "en": "Istiklol",
    },
    "regar-tadaz": {
        "ids": [12268], "aliases": ["regartadaz", "regartadazturzunzoda", "tadaz"],
        "ru": "Регар-ТадАЗ", "tg": "Регар-ТадАЗ",
        "city_ru": "Турсунзаде", "city_tg": "Турсунзода",
        "en": "Regar-TadAZ",
    },
    "khosilot": {
        "ids": [8041], "aliases": ["khosilotfarkhor", "khosilot", "hosilot"],
        "ru": "Хосилот", "tg": "Ҳосилот",
        "city_ru": "Фархор", "city_tg": "Фархор",
        "en": "Khosilot Farkhor",
    },
    "cska-pomir": {
        "ids": [12261], "aliases": ["cskapomir", "cskapamir", "pomirdushanbe", "pamir"],
        "ru": "ЦСКА-Памир", "tg": "ЦСКА-Помир",
        "city_ru": "Душанбе", "city_tg": "Душанбе",
        "en": "CSKA Pomir",
        "files": ["КМВА", "FC CSKA logo png"],
    },
    "khujand": {
        "ids": [8031], "aliases": ["khujand", "khudzhand", "fckhujand"],
        "ru": "Худжанд", "tg": "Хуҷанд",
        "city_ru": "Худжанд", "city_tg": "Хуҷанд",
        "en": "Khujand",
    },
    "ravshan": {
        "ids": [12272], "aliases": ["ravshan", "ravshankulob", "ravshankulyab"],
        "ru": "Равшан", "tg": "Равшан",
        "city_ru": "Куляб", "city_tg": "Кӯлоб",
        "en": "Ravshan Kulob",
    },
    "vakhsh": {
        "ids": [], "aliases": ["vakhsh", "vakhshqurghonteppa", "vakhshbokhtar", "vaksh"],
        "ru": "Вахш", "tg": "Вахш",
        "city_ru": "Бохтар", "city_tg": "Бохтар",
        "en": "Vakhsh",
    },
    "barkchi": {
        "ids": [], "aliases": ["barkchi", "barkchihisor", "barqchi"],
        "ru": "Баркчи", "tg": "Барқчӣ",
        "city_ru": "Гиссар", "city_tg": "Ҳисор",
        "en": "Barqchi Hisor",
    },
    "eskhata": {
        "ids": [16494], "aliases": ["eskhata", "fceskhata", "eskhatakhujand"],
        "ru": "Эсхата", "tg": "Эсхата",
        "city_ru": "Худжанд", "city_tg": "Хуҷанд",
        "en": "Eskhata",
        "files": ["Эсхатанав", "FC ESKHATA logo png"],
    },
    "parvoz": {
        "ids": [], "aliases": ["parvoz", "parvozbobojonghafurov"],
        "ru": "Парвоз", "tg": "Парвоз",
        "city_ru": "Бободжон Гафуров", "city_tg": "Бобоҷон Ғафуров",
        "en": "Parvoz",
    },
    "sardor": {
        "ids": [27266], "aliases": ["sardor", "sardortursunzoda"],
        "ru": "Сардор", "tg": "Сардор",
        "city_ru": "Турсунзаде", "city_tg": "Турсунзода",
        "en": "Sardor",
    },
    "istaravshan": {
        "ids": [12264], "aliases": ["istaravshan", "fcistaravshan"],
        "ru": "Истаравшан", "tg": "Истаравшан",
        "city_ru": "Истаравшан", "city_tg": "Истаравшан",
        "en": "Istaravshan",
    },
    # Ниже — клубы, которых нет в присланном списке, но они встречаются
    # в матчах прошлых сезонов. Без них таблица снова покажет латиницу.
    "khatlon": {
        "ids": [12265], "aliases": ["khatlon", "khatlonbokhtar"],
        "ru": "Хатлон", "tg": "Хатлон",
        "city_ru": "Бохтар", "city_tg": "Бохтар",
        "en": "Khatlon",
    },
    "kuktosh": {
        "ids": [12266], "aliases": ["kuktosh", "kuktoshrudaki"],
        "ru": "Куктош", "tg": "Кӯктош",
        "city_ru": "Рудаки", "city_tg": "Рӯдакӣ",
        "en": "Kuktosh",
    },
    "panjsher": {
        "ids": [12269], "aliases": ["panjsher", "panjsherhisor", "panjshir"],
        "ru": "Панджшер", "tg": "Панҷшер",
        "city_ru": "Гиссар", "city_tg": "Ҳисор",
        "en": "Panjsher",
    },
    "barki-tajik": {
        "ids": [12270], "aliases": ["barkitajik", "barkitojik", "barquitajik"],
        "ru": "Барки Точик", "tg": "Барқи Тоҷик",
        "city_ru": "Душанбе", "city_tg": "Душанбе",
        "en": "Barki Tajik",
    },
    # id пока не встречался — клуб опознаётся по латинскому написанию из API,
    # а эмблема у нас уже есть
    "khulbuk": {
        "ids": [], "aliases": ["khulbuk", "khulbukvose", "hulbuk"],
        "ru": "Хулбук", "tg": "Хулбук",
        "city_ru": "Восе", "city_tg": "Восеъ",
        "en": "Khulbuk",
    },
}

BY_ID = {tid: slug for slug, c in CLUBS.items() for tid in c["ids"]}
BY_ALIAS = {a: slug for slug, c in CLUBS.items() for a in c["aliases"]}


def _norm(name: str | None) -> str:
    """«Khosilot Farkhor» -> «khosilotfarkhor»: убираем всё, кроме букв и цифр."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# Таджикские буквы с диакритикой и их русские двойники: «Ҳосилот» и «Хосилот»
# для поиска должны быть одним и тем же словом.
_FOLD = str.maketrans({"ӣ": "и", "ӯ": "у", "ҳ": "х", "ҷ": "ч", "қ": "к", "ғ": "г", "ё": "е", "ъ": ""})


def _fold(s: str) -> str:
    return (s or "").lower().translate(_FOLD).strip()


# Имя файла эмблемы -> slug. Владелец складывает картинки под русскими и
# таджикскими названиями («Хучанд.png», «Регар-ТадАЗ.png»), а не под слагами,
# поэтому к слагу добавляем оба названия, прогнанные через _fold: он же
# стирает разницу «Хуҷанд»/«Хучанд». Аббревиатуры и прежние написания, которые
# из названия не выводятся (КМВА, Эсхатанав), перечислены в "files".
BY_LOGO_FILE = {
    key: slug
    for slug, c in CLUBS.items()
    for key in {slug, _fold(c["ru"]), _fold(c["tg"]),
                *(_fold(f) for f in c.get("files", ()))}
}


# ------------------------------------------------------------------ эмблемы
# Список файлов кэшируем: страница лиги дёргает эту функцию по разу на клуб,
# а владелец сайта докладывает картинки редко. mtime папки ловит появление
# новых файлов без перезапуска сервиса.
_logo_cache: dict[str, str] = {}
_logo_stamp: tuple[float, float] = (0.0, 0.0)


def _logos() -> dict[str, str]:
    """slug -> путь вида /static/logosligaioli/istiqlol.png"""
    global _logo_cache, _logo_stamp
    try:
        mtime = LOGO_DIR.stat().st_mtime
    except OSError:
        return {}
    now = time.time()
    # перечитываем, если папка изменилась или прошло больше минуты
    if _logo_stamp[0] == mtime and now - _logo_stamp[1] < 60:
        return _logo_cache
    found: dict[str, str] = {}
    for f in sorted(LOGO_DIR.iterdir()):
        if not f.is_file() or f.suffix.lower() not in LOGO_EXTS:
            continue
        slug = BY_LOGO_FILE.get(_fold(f.stem))
        if slug and slug not in found:
            found[slug] = f"/static/{LOGO_DIRNAME}/{f.name}"
    _logo_cache, _logo_stamp = found, (mtime, now)
    return found


# ------------------------------------------------------------------ API модуля
def slug_for(team_id: int | None, name: str | None) -> str | None:
    if team_id is not None and team_id in BY_ID:
        return BY_ID[team_id]
    return BY_ALIAS.get(_norm(name))


def names(team_id: int | None, name: str | None) -> tuple[str, str, str]:
    """(русское имя, таджикское имя, английское имя).

    Сначала смотрим свой справочник Лигаи Олӣ — он выверен вручную и точнее.
    Остальные клубы и сборные ищем в общем справочнике (app/names.py).
    Если команды нет нигде, остаётся латиница из API: это честнее, чем
    показать выдуманное написание.
    """
    slug = slug_for(team_id, name)
    if slug:
        c = CLUBS[slug]
        return c["ru"], c["tg"], c.get("en") or name or c["ru"]
    triple = app_names.team_names(name)
    if triple:
        return triple
    return name or "", name or "", name or ""


def logo_for(team_id: int | None, name: str | None, fallback: str | None) -> str | None:
    slug = slug_for(team_id, name)
    if slug:
        local = _logos().get(slug)
        if local:
            return local
    return fallback


def team_out(team_id: int | None, name: str | None, logo: str | None) -> dict:
    """Единая форма команды для фронта: name — русское, name_tg — таджикское.

    Фронт сам выбирает нужное по языку (см. tname() в static/js/ui.js), поэтому
    переключение языка не требует нового запроса к серверу.
    """
    ru, tg, en = names(team_id, name)
    return {
        "id": team_id,
        "name": ru,
        "name_ru": ru,
        "name_tg": tg,
        "name_en": en,
        "logo": logo_for(team_id, name, logo),
    }


def slugs_matching(q: str) -> set[str]:
    """Слаги клубов, у которых запрос встречается в названии или городе.

    Нужно поиску: в базе клуб лежит как «Istiqlol», а человек набирает
    «Истиклол» или «Истиқлол». Сравниваем без учёта регистра и без «ӣ ӯ ҳ ...»,
    чтобы русское и таджикское написание находили друг друга.
    """
    q = _fold(q)
    if len(q) < 2:
        return set()
    out = set()
    for slug, c in CLUBS.items():
        haystack = " ".join(filter(None, (c["ru"], c["tg"], c.get("city_ru"), c.get("city_tg"))))
        if q in _fold(haystack):
            out.add(slug)
    return out


def city(team_id: int | None, name: str | None) -> tuple[str | None, str | None]:
    slug = slug_for(team_id, name)
    if not slug:
        return None, None
    c = CLUBS[slug]
    return c.get("city_ru"), c.get("city_tg")
