"""Асинхронный клиент football-data.org.

Второй источник данных. В отличие от API-Football здесь нет суточного потолка —
только 10 запросов в минуту, поэтому ограничитель скользящий, по минуте, а не
дневной счётчик.

Запросы сериализованы одним замком: пара параллельных обращений легко
проскакивает мимо ограничителя и ловит 429, после которого сервер держит паузу.
"""
import asyncio
import logging
import time

import httpx

from app.config import (FD_BASE, FD_KEY, FD_SOFT_RATE_PER_MIN, FD_TIMEOUT)

log = logging.getLogger("tajscore.fd")


class FdRateLimited(RuntimeError):
    """Сервер попросил притормозить."""


class FdClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._calls: list[float] = []     # отметки времени запросов за последнюю минуту
        self._blocked_until = 0.0
        self.last_available: int | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=FD_BASE,
                headers={"X-Auth-Token": FD_KEY, "Accept": "application/json"},
                timeout=FD_TIMEOUT,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Держим не больше FD_SOFT_RATE_PER_MIN запросов в скользящую минуту."""
        while True:
            now = time.monotonic()
            if now < self._blocked_until:
                await asyncio.sleep(self._blocked_until - now)
                continue
            self._calls = [t for t in self._calls if now - t < 60]
            if len(self._calls) < FD_SOFT_RATE_PER_MIN:
                self._calls.append(now)
                return
            # ждём, пока освободится самый старый слот
            await asyncio.sleep(60 - (now - self._calls[0]) + 0.05)

    async def get(self, path: str, params: dict | None = None) -> dict | None:
        """Вернёт разобранный JSON либо None при любой ошибке."""
        if not FD_KEY:
            log.error("FOOTBALL_DATA_KEY не задан в .env")
            return None
        async with self._lock:
            await self._throttle()
            client = await self._get_client()
            try:
                r = await client.get(path, params=params or {})
            except Exception as e:
                log.error("сеть %s: %s", path, e)
                return None

            avail = r.headers.get("x-requests-available-minute")
            if avail is not None:
                try:
                    self.last_available = int(avail)
                except ValueError:
                    pass

            if r.status_code == 429:
                wait = int(r.headers.get("x-requestcounter-reset") or 60)
                self._blocked_until = time.monotonic() + wait
                log.warning("football-data: 429, пауза %s с", wait)
                return None
            if r.status_code == 403:
                # тариф не даёт этот турнир/сезон — повторять бессмысленно
                log.warning("football-data %s -> 403 (нет доступа на тарифе)", path)
                return None
            if r.status_code != 200:
                log.error("football-data %s -> HTTP %s: %s", path, r.status_code, r.text[:200])
                return None
            try:
                return r.json()
            except Exception:
                log.error("football-data %s -> не JSON", path)
                return None


fd = FdClient()
