"""HTML-страницы. Разметка приходит сразу, данные подтягивает JS из /api."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.routers.auth import current_user

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _page(request: Request, template: str, page: str, **extra):
    """Страница с именем вошедшего прямо в разметке.

    Иначе кнопка успевает показать «Войти», пока браузер ждёт ответа
    /api/auth/me, — на медленной связи это видно каждое обновление. JS после
    загрузки всё равно обновит шапку, так что серверное значение нужно только
    для первого кадра.

    Раз разметка теперь зависит от посетителя, общим кэшам её отдавать нельзя:
    иначе соседу достанется страница с чужим именем в шапке.
    """
    user = current_user(request)
    ctx = {"request": request, "page": page,
           "auth_name": user["display_name"] if user else None, **extra}
    return templates.TemplateResponse(
        template, ctx, headers={"Cache-Control": "private, no-cache"})


# HEAD нужен аптайм-мониторингам: FastAPI, в отличие от Starlette, сам его к GET не добавляет
@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    return _page(request, "index.html", "home")


@router.get("/match/{fixture_id}", response_class=HTMLResponse)
def match_page(request: Request, fixture_id: int):
    return _page(request, "match.html", "match", fixture_id=fixture_id)


@router.get("/league/{league_id}", response_class=HTMLResponse)
def league_page(request: Request, league_id: int):
    return _page(request, "league.html", "league", league_id=league_id)


@router.get("/team/{team_id}", response_class=HTMLResponse)
def team_page(request: Request, team_id: int):
    return _page(request, "team.html", "team", team_id=team_id)
