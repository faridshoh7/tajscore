"""API настроек уведомлений и подписок web-push."""
from fastapi import APIRouter, Body, HTTPException, Request

from app import auth, db
from app.admin import _parse_device_name
from app.notify import engine
from app.notify import prefs as P
from app.notify import webpush
from app.routers.auth import _require_user, current_user

router = APIRouter(prefix="/api")


def _state(user: dict) -> dict:
    return {
        "enabled": bool(user["notifications_enabled"]),
        "prefs": P.load(user["id"]),
        "telegram": {"linked": bool(user.get("telegram_id")),
                     "blocked": bool(user.get("is_blocked"))},
        "push_devices": webpush.count(user["id"]),
        "options": {"reminder_min": list(P.REMINDER_OPTIONS), "levels": list(P.LEVELS),
                    "events": list(P.EVENTS), "key_events": list(P.KEY_EVENTS)},
    }


@router.get("/notify/prefs")
def get_prefs(request: Request):
    return _state(_require_user(request))


@router.post("/notify/prefs")
def set_prefs(request: Request, enabled: bool | None = Body(None, embed=True),
              prefs: dict | None = Body(None, embed=True)):
    user = _require_user(request)
    if enabled is not None:
        auth.set_notifications(user["id"], enabled)
    if prefs is not None:
        P.save(user["id"], P.merge(P.load(user["id"]), prefs))
    return _state(auth.get_user(user["id"]))


@router.post("/notify/test")
async def test(request: Request):
    import asyncio
    user = await asyncio.to_thread(current_user, request)
    if not user:
        raise HTTPException(401, "Нужно войти через Telegram")
    return await engine.send_test(user)


@router.get("/notify/match/{fixture_id}")
def match_state(request: Request, fixture_id: int):
    """Колокольчик на странице матча: приходят ли по нему уведомления."""
    user = current_user(request)
    if not user:
        return {"auth": False}
    from app.services.common import FIXTURE_SELECT, fixture_row
    row = db.query_one(f"{FIXTURE_SELECT} WHERE f.id=?", (fixture_id,))
    if not row:
        raise HTTPException(404, "Матч не найден")
    fx = fixture_row(row)
    following = any(u["id"] == user["id"] for u, _, _ in engine.subscribers(fx)) \
        if user["notifications_enabled"] else False
    return {"auth": True, "enabled": bool(user["notifications_enabled"]),
            "following": following, "muted": P.is_muted(user["id"], fixture_id)}


@router.post("/notify/mute")
def mute(request: Request, fixture_id: int = Body(..., embed=True),
         muted: bool = Body(..., embed=True)):
    user = _require_user(request)
    P.set_mute(user["id"], fixture_id, muted)
    return {"muted": muted}


# ------------------------------------------------------------------ web-push
@router.get("/push/key")
def push_key():
    return {"key": webpush.public_key()}


@router.post("/push/subscribe")
def push_subscribe(request: Request, subscription: dict = Body(..., embed=True)):
    user = _require_user(request)
    device = _parse_device_name(request.headers.get("user-agent") or "")
    if not webpush.subscribe(user["id"], subscription, device):
        raise HTTPException(400, "Неверная подписка")
    return {"ok": True, "push_devices": webpush.count(user["id"])}


@router.post("/push/unsubscribe")
def push_unsubscribe(request: Request, endpoint: str = Body(..., embed=True, max_length=1000)):
    user = _require_user(request)
    webpush.unsubscribe(user["id"], endpoint)
    return {"ok": True, "push_devices": webpush.count(user["id"])}
