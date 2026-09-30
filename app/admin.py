"""Админка: журнал посещений.

Доступ закрыт HTTP Basic Auth. Пароль берётся из ADMIN_PASSWORD в .env —
если переменная не задана, админка не отвечает вовсе: пустой пароль хуже,
чем выключенный раздел.

IP посетителей — персональные данные. Записи старше RETENTION_DAYS удаляются
при каждом открытии журнала.
"""
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app import db
from app.config import TEMPLATES_DIR

log = logging.getLogger("tajscore.admin")
TZ = timezone(timedelta(hours=5))   # Asia/Dushanbe
router = APIRouter(prefix="/adminpanel")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_dt(ts) -> str:
    """Время показываем по Душанбе — админ смотрит из Таджикистана."""
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), TZ).strftime("%d.%m.%Y %H:%M")


templates.env.filters["dt"] = _fmt_dt
security = HTTPBasic(auto_error=False)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
RETENTION_DAYS = int(os.getenv("VISITS_RETENTION_DAYS", "90"))

# Пути, которые не считаем посещениями: статика, служебное, сама админка
SKIP_PREFIXES = ("/static", "/api", "/adminpanel", "/favicon")


def client_ip(request: Request) -> str:
    """Реальный адрес посетителя.

    Сайт стоит за nginx, поэтому request.client.host — это всегда 127.0.0.1.
    Настоящий адрес приходит в заголовках, которые проставляет прокси.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def record_visit(request: Request) -> None:
    """Пишет заход. Ошибки журнала не должны ронять страницу."""
    path = request.url.path
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return
    try:
        db.execute(
            "INSERT INTO visits (ts, ip, path, ua, ref) VALUES (?,?,?,?,?)",
            (int(time.time()), client_ip(request), path,
             (request.headers.get("user-agent") or "")[:300],
             (request.headers.get("referer") or "")[:300]))
    except Exception:
        log.exception("не удалось записать посещение")


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if not ADMIN_PASSWORD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Админка не настроена")
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход",
                            headers={"WWW-Authenticate": "Basic"})
    # compare_digest — чтобы по времени ответа нельзя было подобрать пароль посимвольно
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _cleanup() -> int:
    edge = int(time.time()) - RETENTION_DAYS * 86400
    cur = db.execute("DELETE FROM visits WHERE ts < ?", (edge,))
    return cur.rowcount if cur else 0


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, _: str = Depends(require_admin), limit: int = 200):
    _cleanup()
    day = int(time.time()) - 86400
    week = int(time.time()) - 7 * 86400
    stats = {
        "total": db.query_one("SELECT COUNT(*) n FROM visits")["n"],
        "uniq": db.query_one("SELECT COUNT(DISTINCT ip) n FROM visits")["n"],
        "day": db.query_one("SELECT COUNT(*) n FROM visits WHERE ts>=?", (day,))["n"],
        "day_uniq": db.query_one("SELECT COUNT(DISTINCT ip) n FROM visits WHERE ts>=?", (day,))["n"],
        "week": db.query_one("SELECT COUNT(*) n FROM visits WHERE ts>=?", (week,))["n"],
        "retention": RETENTION_DAYS,
    }
    visitors = db.query(
        """SELECT ip, COUNT(*) hits, MAX(ts) last, MIN(ts) first,
                  COUNT(DISTINCT path) pages
           FROM visits GROUP BY ip ORDER BY last DESC LIMIT ?""", (limit,))
    recent = db.query(
        "SELECT ts, ip, path, ua, ref FROM visits ORDER BY id DESC LIMIT ?", (limit,))
    pages = db.query(
        "SELECT path, COUNT(*) n FROM visits GROUP BY path ORDER BY n DESC LIMIT 25")
    return templates.TemplateResponse("admin.html", {
        "request": request, "page": "admin", "stats": stats,
        "visitors": [dict(r) for r in visitors],
        "recent": [dict(r) for r in recent],
        "pages": [dict(r) for r in pages],
    })
