"""API входа через Telegram, профиля и избранного.

Сессия живёт в httpOnly-cookie: JS до неё не дотягивается, значит украсть её
через XSS нельзя. Сама cookie заводится ещё для гостя — к ней привязывается
одноразовый login-токен, чтобы подтверждение из бота прилетело именно в тот
браузер, где нажали кнопку.
"""
import logging
import time

from fastapi import APIRouter, Body, HTTPException, Request, Response

from app import auth
from app.config import SESSION_COOKIE, SESSION_TTL, TELEGRAM_BOT_USERNAME

log = logging.getLogger("tajscore.auth.api")
router = APIRouter(prefix="/api/auth")


def _secure(request: Request) -> bool:
    """Сайт за nginx, поэтому про https знаем только из заголовка прокси.
    На локальном http Secure-cookie браузер бы просто выбросил."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def _set_cookie(request: Request, response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id,
        max_age=SESSION_TTL, httponly=True, samesite="lax",
        secure=_secure(request), path="/")


def _session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request) -> dict | None:
    return auth.session_user(_session_id(request))


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Нужно войти через Telegram")
    return user


# ------------------------------------------------------------------ вход
@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return {"user": auth.public_user(user) if user else None}


@router.post("/start")
def start(request: Request, response: Response):
    """Кнопка «Войти через Telegram»: заводим сессию (если её ещё нет)
    и одноразовый токен, отдаём ссылку на бота."""
    if not TELEGRAM_BOT_USERNAME:
        raise HTTPException(503, "Вход через Telegram не настроен")

    user = current_user(request)
    if user:
        return {"already": True, "user": auth.public_user(user)}

    session_id = _session_id(request)
    if not auth.get_session(session_id):
        session_id = auth.create_session()
        _set_cookie(request, response, session_id)

    data = auth.create_login_token(session_id)
    return {"already": False, **data}


@router.get("/poll")
def poll(request: Request, token: str):
    """Сайт опрашивает этот метод, пока человек ходит в бота.

    Статусы: pending — ждём Start; ok — вошли; expired — 5 минут истекли;
    unknown — токен не наш или уже израсходован.
    """
    session_id = _session_id(request)
    row = auth.get_login_token(token)
    if not row or row["session_id"] != session_id:
        return {"status": "unknown"}
    if row["used"]:
        # токен мог быть отработан параллельной вкладкой — смотрим, вошли ли уже
        user = current_user(request)
        return {"status": "ok", "user": auth.public_user(user)} if user else {"status": "unknown"}
    if not row["confirmed"]:
        if row["expires_at"] < int(time.time()):
            return {"status": "expired"}
        return {"status": "pending", "expires_in": row["expires_at"] - int(time.time())}

    user = auth.claim_login_token(token, session_id)
    if not user:
        return {"status": "expired"}
    log.info("вход: telegram_id=%s", user["telegram_id"])
    return {"status": "ok", "user": auth.public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response):
    session_id = _session_id(request)
    if session_id:
        auth.drop_session(session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ------------------------------------------------------------------ профиль
@router.post("/notifications")
def notifications(request: Request, enabled: bool = Body(..., embed=True)):
    user = _require_user(request)
    auth.set_notifications(user["id"], enabled)
    return {"ok": True, "notifications": enabled}


# ------------------------------------------------------------------ избранное
fav_router = APIRouter(prefix="/api/favorites")


@fav_router.get("")
def favorites(request: Request):
    user = current_user(request)
    if not user:
        # гостю избранного не полагается, но и ошибкой это не является
        return {"auth": False, "favorites": {t: [] for t in auth.FAV_TYPES}}
    return {"auth": True, "favorites": auth.list_favorites(user["id"])}


@fav_router.post("/toggle")
def toggle(request: Request, type: str = Body(...), id: int = Body(...)):
    user = _require_user(request)
    if type not in auth.FAV_TYPES:
        raise HTTPException(400, "Неизвестный тип избранного")
    return {"on": auth.toggle_favorite(user["id"], type, id)}


@fav_router.post("/merge")
def merge(request: Request, items: list[dict] = Body(..., embed=True)):
    """Первый вход: переносим на сервер то, что гость успел отметить локально."""
    user = _require_user(request)
    auth.merge_favorites(user["id"], items)
    return {"favorites": auth.list_favorites(user["id"])}
