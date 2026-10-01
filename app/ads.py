"""Рекламные блоки.

Владелец сайта правит один файл — data/ads.json — и кладёт ролики/картинки
в static/ads/. Ни базы, ни админки здесь нет намеренно: реклама должна
включаться и выключаться правкой текстового файла, без перезапуска сервера.

Формат data/ads.json описан в static/ads/README.md.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date

from app.config import DATA_DIR

log = logging.getLogger("tajscore.ads")

ADS_PATH = DATA_DIR / "ads.json"
_CACHE: dict = {"mtime": -1.0, "checked": 0.0, "data": None}
_RECHECK_SEC = 5.0          # как часто заглядываем в файл за изменениями

# Размеры рекламного места. Их же отдаём в /api/ads, чтобы фронт не расходился
# с вёрсткой, а владелец мог свериться прямо в браузере.
SIZES = {
    "desktop": {"width": 1200, "height": 171, "ratio": "7 / 1",
                "recommended": "2400x342 (@2x)"},
    "mobile": {"width": 640, "height": 240, "ratio": "8 / 3",
               "recommended": "1280x480 (@2x)"},
}

_ALLOWED_TYPES = ("video", "image")


def _read_file() -> dict:
    """Читает data/ads.json с кэшем по mtime. Битый JSON не роняет сайт."""
    now = time.monotonic()
    if _CACHE["data"] is not None and now - _CACHE["checked"] < _RECHECK_SEC:
        return _CACHE["data"]
    _CACHE["checked"] = now
    try:
        mtime = ADS_PATH.stat().st_mtime
    except OSError:
        _CACHE["mtime"], _CACHE["data"] = -1.0, {}
        return _CACHE["data"]
    if mtime == _CACHE["mtime"] and _CACHE["data"] is not None:
        return _CACHE["data"]
    try:
        with ADS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("ожидался объект верхнего уровня")
    except Exception as e:                      # noqa: BLE001 — любая ошибка = рекламы нет
        log.warning("data/ads.json не прочитан (%s); показываю заглушку", e)
        data = {}
    _CACHE["mtime"], _CACHE["data"] = mtime, data
    return data


def _in_window(item: dict, today: str) -> bool:
    """Показ ограничивают необязательные поля start/end (ГГГГ-ММ-ДД)."""
    start, end = item.get("start"), item.get("end")
    if start and today < str(start):
        return False
    if end and today > str(end):
        return False
    return True


def _creative(raw) -> dict | None:
    """Нормализует одну картинку/ролик. Без src креатив бессмысленен."""
    if not isinstance(raw, dict):
        return None
    src = str(raw.get("src") or "").strip()
    if not src:
        return None
    kind = str(raw.get("type") or "").strip().lower()
    if kind not in _ALLOWED_TYPES:
        kind = "video" if src.lower().endswith((".mp4", ".webm", ".ogv")) else "image"
    out = {"type": kind, "src": src}
    if raw.get("poster"):
        out["poster"] = str(raw["poster"])
    return out


def active() -> dict:
    """Готовый ответ для /api/ads: только те блоки, что реально можно показать."""
    data = _read_file()
    out = {"enabled": bool(data.get("enabled", True)), "sizes": SIZES, "items": []}
    if not out["enabled"]:
        return out

    today = date.today().isoformat()
    for raw in data.get("items") or []:
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        if not _in_window(raw, today):
            continue
        desktop = _creative(raw.get("desktop"))
        mobile = _creative(raw.get("mobile"))
        # Один креатив на оба размера — нормальная ситуация: подставляем его всюду.
        desktop, mobile = desktop or mobile, mobile or desktop
        if not desktop:
            continue
        try:
            weight = max(1, int(raw.get("weight", 1)))
        except (TypeError, ValueError):
            weight = 1
        out["items"].append({
            "id": str(raw.get("id") or f"ad{len(out['items']) + 1}"),
            "title": str(raw.get("title") or ""),
            "link": str(raw.get("link") or ""),
            "weight": weight,
            "desktop": desktop,
            "mobile": mobile,
        })
    return out
