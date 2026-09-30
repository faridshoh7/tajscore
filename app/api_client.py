"""Асинхронный клиент API-Football. Единственное место, где проект ходит в интернет."""
import asyncio
import logging
import time

import httpx

from app import budget
from app.config import API_BASE, API_HEADER, API_KEY, API_TIMEOUT, MIN_REQUEST_GAP

log = logging.getLogger("tajscore.api")


class BudgetExceeded(RuntimeError):
    """Лимит запросов исчерпан."""


class PlanRestricted(RuntimeError):
    """Тариф не даёт доступа к этому сезону/дате — повторять бессмысленно."""


class ApiClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=API_BASE,
                headers={API_HEADER: API_KEY, "Accept": "application/json"},
                timeout=API_TIMEOUT,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(self, endpoint: str, params: dict, task: str, force: bool = False) -> list | None:
        """Вернёт response-массив API либо None, если бюджет исчерпан / ошибка.

        Запросы сериализованы: два одновременных обращения к API не уйдут никогда,
        иначе счётчик может обогнать лимит.
        """
        async with self._lock:
            if not force and not budget.can_spend(task):
                log.warning("Бюджет исчерпан, пропускаю %s %s", task, endpoint)
                return None
            if not API_KEY:
                log.error("API_FOOTBALL_KEY не задан")
                return None
            # На Free-тарифе действует ещё и поминутный лимит — держим паузу между запросами
            gap = MIN_REQUEST_GAP - (time.monotonic() - self._last_call)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last_call = time.monotonic()
            client = await self._get_client()
            try:
                r = await client.get(endpoint, params=params)
            except Exception as e:  # сеть отвалилась — запрос у api-sports не засчитан
                log.error("Сетевая ошибка %s %s: %s", endpoint, params, e)
                budget.log_call(task, endpoint, params, 0, error=str(e)[:200])
                return None

            rem = r.headers.get("x-ratelimit-requests-remaining")
            try:
                data = r.json()
            except Exception:
                budget.log_call(task, endpoint, params, r.status_code, error="не JSON")
                return None

            errors = data.get("errors") or {}
            if isinstance(errors, dict) and errors:
                msg = "; ".join(f"{k}: {v}" for k, v in errors.items())[:200]
                log.error("API вернул ошибку %s %s -> %s", endpoint, params, msg)
                budget.log_call(task, endpoint, params, r.status_code, remaining_header=rem, error=msg)
                if "rateLimit" in errors or "requests" in errors:
                    raise BudgetExceeded(msg)
                if "plan" in errors:
                    raise PlanRestricted(msg)
                return None

            resp = data.get("response") or []
            budget.log_call(task, endpoint, params, r.status_code, len(resp), rem)
            log.info("API %s %s -> %s записей (осталось у api-sports: %s)",
                     endpoint, params, len(resp), rem)
            return resp


api = ApiClient()
