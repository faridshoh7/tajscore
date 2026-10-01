"""Tajscore — точка входа. FastAPI + фоновый воркер синхронизации."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app import admin, auth as auth_store, db
from app.config import STATIC_DIR
from app.routers import api as api_router
from app.routers import auth as auth_router
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
    log.info("База готова, запускаю воркеры синхронизации")
    # Два источника с разными лимитами крутятся независимо: медленный
    # API-Football не должен задерживать частый опрос football-data.
    jobs = [
        asyncio.create_task(worker.run_forever(), name="tajscore-sync"),
        asyncio.create_task(worker.fd_run_forever(), name="tajscore-fd"),
    ]
    try:
        yield
    finally:
        for t in jobs:
            t.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


app = FastAPI(title="Tajscore", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def track_visits(request: Request, call_next):
    """Журнал заходов для админки. Считаем только успешно отданные страницы —
    статику и /api отсеивает сам record_visit."""
    response = await call_next(request)
    if response.status_code < 400:
        admin.record_visit(request, response)
    return response


app.include_router(api_router.router)
app.include_router(auth_router.router)
app.include_router(auth_router.fav_router)
app.include_router(admin.router)
app.include_router(pages_router.router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
