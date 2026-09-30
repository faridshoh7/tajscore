"""HTML-страницы. Разметка приходит сразу, данные подтягивает JS из /api."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# HEAD нужен аптайм-мониторингам: FastAPI, в отличие от Starlette, сам его к GET не добавляет
@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "page": "home"})


@router.get("/match/{fixture_id}", response_class=HTMLResponse)
def match_page(request: Request, fixture_id: int):
    return templates.TemplateResponse(
        "match.html", {"request": request, "page": "match", "fixture_id": fixture_id})


@router.get("/league/{league_id}", response_class=HTMLResponse)
def league_page(request: Request, league_id: int):
    return templates.TemplateResponse(
        "league.html", {"request": request, "page": "league", "league_id": league_id})


@router.get("/team/{team_id}", response_class=HTMLResponse)
def team_page(request: Request, team_id: int):
    return templates.TemplateResponse(
        "team.html", {"request": request, "page": "team", "team_id": team_id})
