"""Админ-панель Tajscore.

Разделы:
  - Обзор: ключевые метрики одним экраном
  - Пользователи: устройства посетителей (по cookie, не по IP)
  - Контент: лиги, команды, игроки, фото
  - API и парсеры: расход запросов, интервалы, состояние синхронизации
"""
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app import budget, db, ratelimit
from app.config import (
    DAILY_SOFT_LIMIT, FD_SYNC, LEAGUES, ODDS, PHOTOS, SYNC, TEMPLATES_DIR,
)

log = logging.getLogger("tajscore.admin")
TZ = timezone(timedelta(hours=5))
router = APIRouter(prefix="/adminpanel")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_dt(ts) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), TZ).strftime("%d.%m.%Y %H:%M")


def _fmt_ago(ts) -> str:
    if not ts:
        return "—"
    delta = int(time.time()) - int(ts)
    if delta < 60:
        return "только что"
    if delta < 3600:
        return f"{delta // 60} мин назад"
    if delta < 86400:
        return f"{delta // 3600} ч назад"
    return f"{delta // 86400} дн назад"


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["ago"] = _fmt_ago
security = HTTPBasic(auto_error=False)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
RETENTION_DAYS = int(os.getenv("VISITS_RETENTION_DAYS", "90"))
DEVICE_COOKIE = "ts_device"
DEVICE_COOKIE_TTL = 365 * 86400

SKIP_PREFIXES = ("/static", "/api", "/adminpanel", "/favicon")
SKIP_PATHS = ("/sw.js", "/manifest.webmanifest", "/robots.txt", "/sitemap.xml", "/offline")
# Поисковики, превью ссылок в мессенджерах и скрипты — не люди, в статистику не идут
BOT_MARKERS = ("bot", "crawl", "spider", "slurp", "facebookexternalhit", "preview",
               "curl", "wget", "python", "httpx", "go-http", "java/", "headless",
               "lighthouse", "uptime", "monitor", "scan")


def _parse_device_name(ua: str) -> str:
    """Краткое имя устройства из User-Agent."""
    if not ua:
        return "Неизвестно"
    ua_lower = ua.lower()
    device = ""
    browser = ""
    if "iphone" in ua_lower:
        device = "iPhone"
    elif "ipad" in ua_lower:
        device = "iPad"
    elif "android" in ua_lower:
        m = re.search(r"Android[^;)]*;\s*([^;)]+)", ua, re.I)
        device = m.group(1).strip().split(" Build")[0] if m else "Android"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        device = "Mac"
    elif "windows" in ua_lower:
        device = "Windows"
    elif "linux" in ua_lower:
        device = "Linux"
    elif "bot" in ua_lower or "crawl" in ua_lower or "spider" in ua_lower:
        return "Бот"
    else:
        device = "Другое"

    if "edg" in ua_lower:
        browser = "Edge"
    elif "opr" in ua_lower or "opera" in ua_lower:
        browser = "Opera"
    elif "yabrowser" in ua_lower:
        browser = "Yandex"
    elif "chrome" in ua_lower or "crios" in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower or "fxios" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower:
        browser = "Safari"
    else:
        browser = ""

    return f"{device} / {browser}" if browser else device


def record_visit(request: Request, response: Response) -> None:
    """Регистрирует заход. Устройство определяется по cookie, не по IP."""
    path = request.url.path
    if any(path.startswith(p) for p in SKIP_PREFIXES) or path in SKIP_PATHS:
        return
    if request.method != "GET":
        return          # HEAD шлют мониторинги аптайма — это не посетители
    ua_low = (request.headers.get("user-agent") or "").lower()
    if not ua_low or any(b in ua_low for b in BOT_MARKERS):
        return
    try:
        device_id = request.cookies.get(DEVICE_COOKIE)
        if not device_id:
            device_id = uuid.uuid4().hex
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme
            response.set_cookie(
                DEVICE_COOKIE, device_id,
                max_age=DEVICE_COOKIE_TTL, httponly=True, samesite="lax",
                secure=proto == "https")

        now = int(time.time())
        ua = (request.headers.get("user-agent") or "")[:400]
        name = _parse_device_name(ua)

        db.execute(
            """INSERT INTO devices (device_id, device_name, ua, first_seen, last_seen, visits)
               VALUES (?,?,?,?,?,1)
               ON CONFLICT(device_id) DO UPDATE SET
                   last_seen=excluded.last_seen,
                   visits=devices.visits+1,
                   device_name=COALESCE(devices.device_name, excluded.device_name)""",
            (device_id, name, ua, now, now))

        db.execute(
            "INSERT INTO visits (ts, ip, path, ua, ref) VALUES (?,?,?,?,?)",
            (now, device_id, path, ua[:300],
             (request.headers.get("referer") or "")[:300]))
    except Exception:
        log.exception("не удалось записать посещение")


def require_admin(request: Request,
                  credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Basic Auth с защитой от подбора: после 5 неверных паролей за 15 минут
    адрес блокируется на 30 минут, а админу в лог пишется предупреждение."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Админка не настроена")
    ip = ratelimit.client_ip(request)
    left = ratelimit.admin_locked(ip)
    if left:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Слишком много неверных попыток. Повторите через {left // 60 + 1} мин.",
                            headers={"Retry-After": str(left)})
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход",
                            headers={"WWW-Authenticate": "Basic"})
    ok_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (ok_user and ok_pass):
        if ratelimit.admin_failed(ip):
            log.warning("админка: адрес %s заблокирован после серии неверных паролей", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль",
                            headers={"WWW-Authenticate": "Basic"})
    ratelimit.admin_ok(ip)
    return credentials.username


def _cleanup() -> None:
    edge = int(time.time()) - RETENTION_DAYS * 86400
    db.execute("DELETE FROM visits WHERE ts < ?", (edge,))
    db.execute("DELETE FROM devices WHERE last_seen < ?", (edge,))


def _user_stats() -> dict:
    """Статистика посещений по устройствам."""
    now = int(time.time())
    day_ago = now - 86400
    week_ago = now - 7 * 86400
    month_ago = now - 30 * 86400
    one = lambda sql, p=(): (db.query_one(sql, p) or {"n": 0})["n"]

    return {
        "total_devices": one("SELECT COUNT(*) n FROM devices"),
        "today_devices": one("SELECT COUNT(*) n FROM devices WHERE last_seen >= ?", (day_ago,)),
        "week_devices": one("SELECT COUNT(*) n FROM devices WHERE last_seen >= ?", (week_ago,)),
        "month_devices": one("SELECT COUNT(*) n FROM devices WHERE last_seen >= ?", (month_ago,)),
        "today_visits": one("SELECT COUNT(*) n FROM visits WHERE ts >= ?", (day_ago,)),
        "week_visits": one("SELECT COUNT(*) n FROM visits WHERE ts >= ?", (week_ago,)),
        "month_visits": one("SELECT COUNT(*) n FROM visits WHERE ts >= ?", (month_ago,)),
        "total_visits": one("SELECT COUNT(*) n FROM visits"),
        "registered_users": one("SELECT COUNT(*) n FROM users"),
        "today_new_devices": one("SELECT COUNT(*) n FROM devices WHERE first_seen >= ?", (day_ago,)),
    }


def _content_stats() -> dict:
    one = lambda sql, p=(): (db.query_one(sql, p) or {"n": 0})["n"]
    return {
        "leagues": one("SELECT COUNT(*) n FROM leagues"),
        "teams": one("SELECT COUNT(DISTINCT id) n FROM teams"),
        "fixtures": one("SELECT COUNT(*) n FROM fixtures"),
        "players_total": one("SELECT COUNT(*) n FROM person_names"),
        "players_with_photo": one("SELECT COUNT(*) n FROM person_names WHERE photo IS NOT NULL"),
        "players_checked": one("SELECT COUNT(*) n FROM person_names WHERE checked_at > 0"),
        "players_found_ru": one("SELECT COUNT(*) n FROM person_names WHERE ru IS NOT NULL"),
        "odds_active": one("SELECT COUNT(*) n FROM odds WHERE updated_at > ?",
                           (int(time.time()) - ODDS["max_age"],)),
    }


def _api_stats() -> dict:
    """Расход запросов и состояние синхронизации."""
    from app.sync import worker
    from app.sync.fd_client import fd
    from app.sync.fdorg import COMPETITIONS

    api_football = budget.stats(worker.active_pools())

    fd_state = worker._fd_state
    fd_info = {
        "rate_per_min": FD_SYNC.get("live_interval", 25),
        "soft_rate": 8,
        "available_minute": fd.last_available,
        "live_mode": fd_state.get("live_mode", False),
        "last_tick": fd_state.get("last_tick", 0),
        "running": fd_state.get("running", False),
        "leagues": len(COMPETITIONS),
    }

    sync_states = {}
    rows = db.query("SELECT * FROM sync_state ORDER BY key")
    for r in rows:
        sync_states[r["key"]] = dict(r)

    return {
        "api_football": api_football,
        "fd": fd_info,
        "sync_states": sync_states,
    }


def _devices_list(limit: int = 100) -> list[dict]:
    rows = db.query(
        """SELECT device_id, device_name, first_seen, last_seen, visits
           FROM devices ORDER BY last_seen DESC LIMIT ?""", (limit,))
    return [dict(r) for r in rows]


def _popular_pages(limit: int = 20) -> list[dict]:
    day_ago = int(time.time()) - 86400
    rows = db.query(
        """SELECT path, COUNT(*) n FROM visits WHERE ts >= ?
           GROUP BY path ORDER BY n DESC LIMIT ?""", (day_ago, limit))
    return [dict(r) for r in rows]


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, _: str = Depends(require_admin), tab: str = "overview"):
    _cleanup()

    data = {
        "request": request,
        "page": "admin",
        "tab": tab,
        "users": _user_stats(),
        "content": _content_stats(),
        "api": _api_stats(),
        "devices": _devices_list(),
        "pages": _popular_pages(),
        "leagues_config": LEAGUES,
        "intervals": {
            "api_football_live": SYNC["primary_live_interval"],
            "api_football_live_other": SYNC["live_interval"],
            "api_football_fixtures": SYNC["fixtures_today_interval"],
            "fd_live": FD_SYNC["live_interval"],
            "fd_standings": FD_SYNC["standings_interval"],
            "fd_scorers": FD_SYNC["scorers_interval"],
            "odds": ODDS["interval"],
            "odds_gap": ODDS["request_gap"],
            "photos": PHOTOS["interval"],
            "photos_batch": PHOTOS["batch"],
            "wikidata": FD_SYNC["names_interval"],
        },
        "retention": RETENTION_DAYS,
    }
    return templates.TemplateResponse("admin.html", data)


@router.get("/api/status")
def admin_status(_: str = Depends(require_admin)):
    """Диагностика воркеров и бюджета. Раньше висела открытой на /api/status —
    по ней любой видел устройство сайта и остаток лимита."""
    from app.sync import worker
    counts = {t: db.query_one(f"SELECT COUNT(*) n FROM {t}")["n"]
              for t in ("fixtures", "teams", "fixture_events", "standings", "player_stats")}
    return {"worker": worker.status(), "db": counts, "budget": budget.stats()}


@router.get("/api/stats", response_class=HTMLResponse)
def admin_api_refresh(request: Request, _: str = Depends(require_admin)):
    """HTMX-совместимый эндпоинт для подгрузки обновлённых данных."""
    return admin_page(request, _, tab="api")
