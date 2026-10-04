"""Отправка сообщений в Telegram напрямую через Bot API.

Сайт и бот — разные процессы. Уведомления рождаются на стороне сайта (там
воркеры видят изменение счёта), поэтому отправлять их удобнее отсюда же,
простым HTTPS-запросом, без aiogram. Бот при этом продолжает принимать
нажатия кнопок «Не уведомлять» — их callback_data он понимает сам.

Лимиты Telegram: ~30 сообщений в секунду всего и ~1 в секунду в один чат.
Держимся ниже: глобальная пауза между сообщениями.
"""
import asyncio
import logging
import time

import httpx

from app.config import TELEGRAM_BOT_TOKEN

log = logging.getLogger("tajscore.notify.tg")

API = "https://api.telegram.org/bot{token}/{method}"
GAP = 0.05                # 20 сообщений в секунду максимум

_client: httpx.AsyncClient | None = None
_lock = asyncio.Lock()
_last = 0.0


class Blocked(Exception):
    """Пользователь заблокировал бота или удалил чат."""


async def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30)
    return _client


async def close() -> None:
    if _client and not _client.is_closed:
        await _client.aclose()


async def _call(method: str, data: dict | None = None, files: dict | None = None) -> dict | None:
    """Вызов Bot API с паузой и повтором после 429. Blocked — если чат недоступен."""
    global _last
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    for _attempt in range(3):
        async with _lock:
            wait = GAP - (time.monotonic() - _last)
            if wait > 0:
                await asyncio.sleep(wait)
            _last = time.monotonic()
        try:
            client = await _http()
            if files:
                r = await client.post(url, data=data, files=files, timeout=120)
            else:
                r = await client.post(url, json=data)
            body = r.json()
        except Exception as e:
            # токен в адресе запроса — в лог его не пишем
            log.warning("Telegram %s: сеть: %s", method, type(e).__name__)
            return None
        if body.get("ok"):
            return body.get("result")
        code = body.get("error_code")
        desc = str(body.get("description", ""))
        if code == 429:
            retry = int((body.get("parameters") or {}).get("retry_after", 3))
            await asyncio.sleep(min(retry, 30))
            continue
        if code == 403 or "chat not found" in desc or "user is deactivated" in desc:
            raise Blocked(desc)
        log.warning("Telegram %s -> %s %s", method, code, desc[:200])
        return None
    return None


async def send_message(chat_id: int, text: str, buttons: list[list[dict]] | None = None,
                       silent: bool = False) -> bool:
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True, "disable_notification": silent}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    return await _call("sendMessage", data) is not None


async def send_document(chat_id: int, filename: str, content: bytes, caption: str = "") -> bool:
    data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}
    files = {"document": (filename, content, "application/octet-stream")}
    try:
        return await _call("sendDocument", data, files) is not None
    except Blocked:
        return False


def match_buttons(url: str, fixture_id: int, open_text: str, mute_text: str) -> list[list[dict]]:
    return [
        [{"text": open_text, "url": url}],
        [{"text": mute_text, "callback_data": f"mute:{fixture_id}"}],
    ]


