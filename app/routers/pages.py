"""HTML-страницы. Разметка приходит сразу, данные подтягивает JS из /api.

Заголовок, описание и превью для соцсетей сервер подставляет сам: поисковики и
Telegram при показе ссылки JS не выполняют, и без этого все матчи выглядели бы
для них одинаково — «Матч — Tajscore».
"""
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from app import db, teams_tj
from app.config import LEAGUE_BY_ID, SITE_URL, STATIC_DIR, TEMPLATES_DIR
from app.routers.auth import current_user
from app.services.common import FIXTURE_SELECT, phase

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
TZ = timezone(timedelta(hours=5))   # Душанбе — время в заголовках


def _page(request: Request, template: str, page: str, status_code: int = 200, **extra):
    """Страница с именем вошедшего прямо в разметке.

    Иначе кнопка успевает показать «Войти», пока браузер ждёт ответа
    /api/auth/me, — на медленной связи это видно каждое обновление. JS после
    загрузки всё равно обновит шапку, так что серверное значение нужно только
    для первого кадра.

    Раз разметка теперь зависит от посетителя, общим кэшам её отдавать нельзя:
    иначе соседу достанется страница с чужим именем в шапке.
    """
    user = current_user(request)
    ctx = {"request": request, "page": page, "site_url": SITE_URL,
           "canonical": SITE_URL + request.url.path,
           "auth_name": user["display_name"] if user else None, **extra}
    return templates.TemplateResponse(
        template, ctx, status_code=status_code,
        headers={"Cache-Control": "private, no-cache"})


def not_found(request: Request):
    return _page(request, "404.html", "404", status_code=404,
                 meta_title="Страница не найдена — Tajscore", noindex=True)


# HEAD нужен аптайм-мониторингам: FastAPI, в отличие от Starlette, сам его к GET не добавляет
@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    return _page(request, "index.html", "home",
                 meta_title="Tajscore — футбол онлайн: Лигаи Олӣ, счёт матчей в реальном времени")


@router.get("/match/{fixture_id}", response_class=HTMLResponse)
def match_page(request: Request, fixture_id: int):
    r = db.query_one(f"{FIXTURE_SELECT} WHERE f.id=?", (fixture_id,))
    if not r:
        return not_found(request)
    home = teams_tj.names(r["home_id"], r["home_name"])[0]
    away = teams_tj.names(r["away_id"], r["away_name"])[0]
    league = (LEAGUE_BY_ID.get(r["league_id"]) or {}).get("name_ru", "")
    when = datetime.fromtimestamp(r["timestamp"] or 0, TZ)
    ph = phase(r["status_short"])
    if ph in ("live", "finished") and r["home_goals"] is not None:
        score = f"{r['home_goals']}:{r['away_goals']}"
        title = f"{home} — {away} {score}"
        state = "идёт сейчас, счёт онлайн" if ph == "live" else f"итог {score}"
    else:
        title = f"{home} — {away}"
        state = f"начало {when:%d.%m.%Y} в {when:%H:%M} (Душанбе)"
    desc = (f"{home} — {away}, {league}: {state}. Голы, составы, статистика, "
            f"форма команд и личные встречи на Tajscore.")
    return _page(request, "match.html", "match", fixture_id=fixture_id,
                 meta_title=f"{title} · {league}, {when:%d.%m.%Y} — Tajscore",
                 meta_desc=desc, seo_h1=f"{home} — {away}")


@router.get("/league/{league_id}", response_class=HTMLResponse)
def league_page(request: Request, league_id: int):
    cfg = LEAGUE_BY_ID.get(league_id)
    if not cfg:
        return not_found(request)
    name = cfg["name_ru"]
    return _page(request, "league.html", "league", league_id=league_id,
                 meta_title=f"{name}: таблица, результаты, календарь — Tajscore",
                 meta_desc=f"{name} ({cfg['country_ru']}): турнирная таблица, результаты и "
                           f"расписание матчей, бомбардиры, счёт онлайн.",
                 seo_h1=name)


@router.get("/team/{team_id}", response_class=HTMLResponse)
def team_page(request: Request, team_id: int):
    r = db.query_one("SELECT id, name FROM teams WHERE id=?", (team_id,))
    if not r:
        return not_found(request)
    name = teams_tj.names(r["id"], r["name"])[0]
    return _page(request, "team.html", "team", team_id=team_id,
                 meta_title=f"{name}: матчи, результаты, расписание — Tajscore",
                 meta_desc=f"{name}: последние результаты, ближайшие матчи и счёт онлайн. "
                           f"Уведомления о голах в Telegram.",
                 seo_h1=name)


@router.get("/offline", response_class=HTMLResponse)
def offline(request: Request):
    """Страница, которую приложение показывает без интернета (её кэширует sw.js)."""
    return templates.TemplateResponse("offline.html", {"request": request})


# ------------------------------------------------------------------ PWA и поисковики
@router.get("/sw.js")
def service_worker():
    # Сервис-воркер обязан лежать в корне сайта, иначе он не управляет страницами
    return FileResponse(STATIC_DIR / "js" / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@router.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "img" / "logo-96.png", media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return (
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Disallow: /adminpanel\n"
        "Allow: /\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
def sitemap():
    """Лиги, команды и матчи окна «две недели назад — две недели вперёд»."""
    import time
    now = int(time.time())
    urls = [(f"{SITE_URL}/", "always", "1.0")]
    urls += [(f"{SITE_URL}/league/{lid}", "hourly", "0.8") for lid in LEAGUE_BY_ID]
    for r in db.query(
            """SELECT DISTINCT t.id FROM teams t JOIN fixtures f ON f.home_id=t.id OR f.away_id=t.id
               WHERE f.timestamp > ? LIMIT 3000""", (now - 120 * 86400,)):
        urls.append((f"{SITE_URL}/team/{r['id']}", "daily", "0.6"))
    for r in db.query("SELECT id FROM fixtures WHERE timestamp BETWEEN ? AND ? LIMIT 5000",
                      (now - 14 * 86400, now + 14 * 86400)):
        urls.append((f"{SITE_URL}/match/{r['id']}", "hourly", "0.5"))
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, prio in urls:
        body.append(f"<url><loc>{xml_escape(loc)}</loc><changefreq>{freq}</changefreq>"
                    f"<priority>{prio}</priority></url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


