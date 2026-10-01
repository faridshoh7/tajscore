"""JSON API сайта. Читает ТОЛЬКО SQLite — наружу отсюда запросов нет."""
from fastapi import APIRouter, HTTPException, Query

from app import ads as ads_store
from app import analytics, budget, db
from app.config import DEFAULT_TZ
from app.services import feed as feed_svc
from app.services import league as league_svc
from app.services import match as match_svc
from app.services import search as search_svc
from app.sync import worker

router = APIRouter(prefix="/api")


@router.get("/leagues")
def leagues():
    return {"leagues": feed_svc.sidebar_leagues()}


@router.get("/matches")
def matches(tab: str = "today", tz: str = DEFAULT_TZ, date: str | None = None):
    return feed_svc.feed(tab, tz, date)


@router.get("/matches/live")
def live():
    """Лёгкий ответ для автообновления счёта на странице."""
    return feed_svc.live_scores()


@router.get("/popular")
def popular():
    return {"matches": feed_svc.popular()}


@router.get("/matches/{fixture_id}")
def match_detail(fixture_id: int):
    data = match_svc.get_match(fixture_id)
    if not data:
        raise HTTPException(404, "Матч не найден")
    # просим воркер обновить карточку, если она устарела (сам запрос уйдёт в фоне)
    data["refresh_queued"] = worker.request_detail(fixture_id)
    return data


@router.get("/leagues/{league_id}")
def league_page(league_id: int):
    data = league_svc.page(league_id)
    if not data:
        raise HTTPException(404, "Лига не найдена")
    return data


@router.get("/leagues/{league_id}/standings")
def league_standings(league_id: int):
    return {"standings": league_svc.standings(league_id)}


@router.get("/leagues/{league_id}/fixtures")
def league_fixtures(league_id: int, kind: str = "upcoming", grouped: bool = False):
    if grouped:
        return {"rounds": league_svc.by_round(league_id, kind)}
    return {"matches": league_svc.fixtures(league_id, kind)}


@router.get("/leagues/{league_id}/players")
def league_players(league_id: int, category: str = "goals", limit: int = Query(20, le=50)):
    return {"players": league_svc.players(league_id, category, limit)}


@router.get("/teams/{team_id}")
def team(team_id: int):
    data = search_svc.team_page(team_id)
    if not data:
        raise HTTPException(404, "Команда не найдена")
    return data


@router.get("/search")
def search(q: str = ""):
    return search_svc.search(q)


@router.get("/status")
def status():
    """Диагностика: расход лимита, состояние воркера, объём базы."""
    counts = {t: db.query_one(f"SELECT COUNT(*) n FROM {t}")["n"]
              for t in ("fixtures", "teams", "fixture_events", "standings", "player_stats")}
    return {"worker": worker.status(), "db": counts, "budget": budget.stats()}


@router.get("/ads")
def ads():
    """Рекламные блоки из data/ads.json. Пустой список = показываем заглушку."""
    return ads_store.active()


@router.get("/health")
def health():
    return {"ok": True}
