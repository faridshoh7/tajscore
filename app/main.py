"""Tajscore — точка входа. FastAPI + фоновый воркер синхронизации."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import admin, auth as auth_store, db, ratelimit
from app.config import STATIC_DIR
from app.notify import engine as notify_engine
from app.routers import api as api_router
from app.routers import auth as auth_router
from app.routers import notify as notify_router
from app.routers import pages as pages_router
from app.sync import worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tajscore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    auth_store.cleanup()   # чистим протухшие сессии и login-токены
    log.info("База готова, запускаю воркеры синхронизации и уведомлений")
    # Два источника с разными лимитами крутятся независимо: медленный
    # API-Football не должен задерживать частый опрос football-data.
    jobs = [
        asyncio.create_task(worker.run_forever(), name="tajscore-sync"),
        asyncio.create_task(worker.fd_run_forever(), name="tajscore-fd"),
        asyncio.create_task(notify_engine.run_forever(), name="tajscore-notify"),
    ]
    try:
        yield
    finally:
        for t in jobs:
            t.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


# Документация API (/api/docs) наружу не нужна: по ней удобно изучать сайт
# для атаки, а пользы посетителям никакой.
app = FastAPI(title="Tajscore", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)

# Content-Security-Policy. Встроенные скрипты в шаблонах есть (тема до первой
# отрисовки, инициализация страниц), поэтому 'unsafe-inline' для скриптов
# пока нужен; зато подгрузить скрипт с чужого сайта уже нельзя.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "media-src 'self' https:",
    "connect-src 'self'",
    "worker-src 'self'",
    "manifest-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


@app.middleware("http")
async def guard(request: Request, call_next):
    """Лимит частоты запросов, заголовки безопасности и журнал заходов."""
    wait = ratelimit.check(request)
    if wait:
        return JSONResponse({"detail": "Слишком много запросов, подождите немного"},
                            status_code=429, headers={"Retry-After": str(wait)})
    response = await call_next(request)

    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Content-Security-Policy", CSP)
    if (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    path = request.url.path
    if path.startswith("/static/"):
        # файлы версионируются через ?v=…, поэтому их можно кэшировать надолго
        if request.url.query:
            h["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            h.setdefault("Cache-Control", "public, max-age=86400")
    elif path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")

    if response.status_code < 400:
        # запись в SQLite синхронная — уводим из цикла событий
        await asyncio.to_thread(admin.record_visit, request, response)
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    """Для страниц — человеческая 404, для /api — JSON, как и раньше."""
    if exc.status_code == 404 and not request.url.path.startswith(("/api/", "/static/", "/adminpanel")):
        return await asyncio.to_thread(pages_router.not_found, request)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


app.include_router(api_router.router)
app.include_router(auth_router.router)
app.include_router(auth_router.fav_router)
app.include_router(notify_router.router)
app.include_router(admin.router)
app.include_router(pages_router.router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
