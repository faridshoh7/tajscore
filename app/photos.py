"""Портреты игроков с Викисклада.

Снимок берётся по цепочке: у человека уже известен идентификатор Wikidata
(его сохранил app/wikidata.py, когда искал русское написание имени), у записи
есть свойство P18 — файл на Викискладе, а файл отдаётся по прямой ссылке
с нужной шириной.

Картинка не отдаётся с чужого сервера, а скачивается, обрезается под 3:4 и
кладётся на наш диск. Так список бомбардиров не зависит от доступности
Викисклада и не прыгает из-за разных пропорций исходников.

Автор и лицензия сохраняются, хотя сейчас не показываются: почти все снимки
под CC BY-SA, где подпись обязательна. Понадобится — данные уже лежат.
"""
import asyncio
import io
import logging
import pathlib
import re
import time
import urllib.parse

import httpx
from PIL import Image

from app import db
from app.config import PHOTOS, STATIC_DIR

log = logging.getLogger("tajscore.photos")

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"
UA = "Tajscore/1.0 (https://tajscore.duckdns.org; football scores site)"

PHOTO_DIR = STATIC_DIR / "players"
WEB_PREFIX = "/static/players"


def _slug(latin: str) -> str:
    """Имя файла из латинского имени: предсказуемое и безопасное для пути."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", latin.strip().lower()).strip("-")
    return s[:60] or "player"


def _crop_34(data: bytes) -> bytes | None:
    """Обрезает снимок под 3:4 и ужимает до нужной ширины.

    Срез берётся не по центру, а выше: на спортивных фотографиях лицо почти
    всегда в верхней трети, и центральная обрезка регулярно срезала бы голову.
    """
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        log.debug("не картинка: %s", e)
        return None
    im = im.convert("RGB")
    w, h = im.size
    target = 3 / 4
    if w / h > target:                      # слишком широкая — режем по бокам
        new_w = int(h * target)
        left = (w - new_w) // 2
        im = im.crop((left, 0, left + new_w, h))
    else:                                   # слишком высокая — режем снизу
        new_h = int(w / target)
        top = int((h - new_h) * PHOTOS["crop_top"])
        im = im.crop((0, top, w, top + new_h))
    im = im.resize((PHOTOS["width"], int(PHOTOS["width"] / target)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=PHOTOS["quality"], optimize=True, progressive=True)
    return out.getvalue()


class Fetcher:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": UA}, timeout=PHOTOS["timeout"],
                follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def json(self, url: str, params: dict) -> dict | None:
        try:
            r = await (await self.client()).get(url, params=params)
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            log.debug("запрос %s: %s", url, e)
            return None

    async def raw(self, url: str) -> bytes | None:
        try:
            r = await (await self.client()).get(url)
            return r.content if r.status_code == 200 else None
        except Exception as e:
            log.debug("загрузка %s: %s", url, e)
            return None


fetcher = Fetcher()


async def _files_for(qids: list[str]) -> dict[str, str]:
    """qid -> имя файла на Викискладе (свойство P18)."""
    out = {}
    data = await fetcher.json(WD_API, {"action": "wbgetentities", "ids": "|".join(qids),
                                       "props": "claims", "format": "json"})
    for qid, ent in ((data or {}).get("entities") or {}).items():
        claims = (ent or {}).get("claims") or {}
        for snak in claims.get("P18") or []:
            try:
                out[qid] = snak["mainsnak"]["datavalue"]["value"]
                break
            except Exception:
                continue
    return out


async def _credit(fname: str) -> tuple[str | None, str | None]:
    """(автор, лицензия) — на будущее, если решим показывать подпись."""
    data = await fetcher.json(COMMONS_API, {
        "action": "query", "titles": "File:" + fname, "prop": "imageinfo",
        "iiprop": "extmetadata", "format": "json"})
    try:
        page = next(iter((data["query"]["pages"]).values()))
        md = page["imageinfo"][0]["extmetadata"]
    except Exception:
        return None, None
    strip = lambda v: re.sub(r"<[^>]+>", "", str(v or "")).strip() or None
    return (strip(md.get("Artist", {}).get("value")),
            strip(md.get("LicenseShortName", {}).get("value")))


def _mark(latin: str, photo=None, author=None, lic=None) -> None:
    db.execute(
        """UPDATE person_names SET photo=?, photo_author=?, photo_license=?,
               photo_checked_at=? WHERE latin=?""",
        (photo, author, lic, int(time.time()), latin))


async def fetch_one(latin: str, qid: str, fname: str | None = None) -> bool:
    """Скачивает и обрезает портрет. fname можно передать готовым: список файлов
    выгоднее запрашивать пачкой, Wikidata отдаёт до 50 записей за раз."""
    if fname is None:
        fname = (await _files_for([qid])).get(qid)
    if not fname:
        _mark(latin)                       # фото нет — помечаем, чтобы не искать снова
        return False
    url = FILEPATH + urllib.parse.quote(fname.replace(" ", "_")) + f"?width={PHOTOS['source_width']}"
    raw = await fetcher.raw(url)
    if not raw:
        _mark(latin)
        return False
    jpg = _crop_34(raw)
    if not jpg:
        _mark(latin)
        return False
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(latin)}-{qid.lower()}.jpg"
    (PHOTO_DIR / name).write_bytes(jpg)
    author, lic = await _credit(fname)
    _mark(latin, f"{WEB_PREFIX}/{name}", author, lic)
    return True


def pending(limit: int = 30) -> list[tuple[str, str]]:
    """Игроки без портрета, которых ещё не проверяли.

    Клубы Лигаи Олӣ исключены: их фотографий на Викискладе почти нет, а
    эмблемы и имена для них ведутся вручную.
    Сначала бомбардиры — их и видно в списках.
    """
    rows = db.query(
        """SELECT p.latin, p.qid, MAX(s.value) v FROM person_names p
           JOIN player_stats s ON s.name = p.latin
           WHERE p.qid IS NOT NULL AND p.photo_checked_at = 0
             AND s.league_id != ?
           GROUP BY p.latin, p.qid
           ORDER BY v DESC LIMIT ?""",
        (PHOTOS["skip_league"], limit))
    return [(r["latin"], r["qid"]) for r in rows]


async def sync(limit: int = 30) -> dict:
    todo = pending(limit)
    if not todo:
        return {"checked": 0, "found": 0}

    # Сначала одним махом узнаём, у кого вообще есть снимок: так на людей без
    # фото не тратится отдельный запрос, а их заметная доля.
    files: dict[str, str] = {}
    qids = [q for _, q in todo]
    for i in range(0, len(qids), 50):
        files.update(await _files_for(qids[i:i + 50]))
        await asyncio.sleep(PHOTOS["gap"])

    found = 0
    for latin, qid in todo:
        fname = files.get(qid)
        if not fname:
            _mark(latin)
            continue
        try:
            if await fetch_one(latin, qid, fname):
                found += 1
        except Exception:
            log.exception("портрет %s", latin)
            _mark(latin)
        await asyncio.sleep(PHOTOS["gap"])
    log.info("Портреты: проверено %s, загружено %s", len(todo), found)
    return {"checked": len(todo), "found": found}


def photo_of(latin: str | None) -> str | None:
    if not latin:
        return None
    row = db.query_one("SELECT photo FROM person_names WHERE latin=?", (latin,))
    return row["photo"] if row else None


def credit_of(latin: str | None) -> dict | None:
    """Фото с автором и лицензией. Снимки Викисклада почти все под CC BY-SA,
    где указание автора — обязательное условие использования."""
    if not latin:
        return None
    row = db.query_one("SELECT photo, photo_author, photo_license FROM person_names WHERE latin=?", (latin,))
    if not row or not row["photo"]:
        return None
    return {"photo": row["photo"], "author": row["photo_author"], "license": row["photo_license"]}
