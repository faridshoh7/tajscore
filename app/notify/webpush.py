"""Web-push: уведомления в браузер и в установленное приложение (PWA).

Работает в Chrome/Edge/Firefox/Opera на Android и компьютере, а на iPhone —
в приложении, добавленном на экран «Домой» (iOS 16.4+). Когда сайт станет
APK-приложением (TWA), эти же подписки продолжат работать.

Ключи VAPID создаются один раз при первом запуске и лежат в data/vapid.json
(в git не попадают). Если файл потерять, все подписки придётся оформить
заново — браузеры привязывают их к публичному ключу.
"""
import asyncio
import base64
import json
import logging
import time

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

from app import db
from app.config import DATA_DIR, SITE_URL

log = logging.getLogger("tajscore.notify.push")

KEY_FILE = DATA_DIR / "vapid.json"
_vapid: Vapid01 | None = None
_public: str | None = None


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _load() -> None:
    global _vapid, _public
    if _vapid is not None:
        return
    if KEY_FILE.exists():
        data = json.loads(KEY_FILE.read_text())
        v = Vapid01.from_pem(data["private_pem"].encode())
    else:
        v = Vapid01()
        v.generate_keys()
        pem = v.private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_text(json.dumps({"private_pem": pem}))
        try:
            KEY_FILE.chmod(0o600)
        except OSError:
            pass
        log.info("Созданы ключи VAPID для web-push: %s", KEY_FILE)
    raw = v.public_key.public_bytes(serialization.Encoding.X962,
                                    serialization.PublicFormat.UncompressedPoint)
    _vapid, _public = v, _b64url(raw)


def public_key() -> str:
    _load()
    return _public or ""


# ------------------------------------------------------------------ подписки
def subscribe(user_id: int, sub: dict, device: str | None) -> bool:
    """Сохраняет подписку браузера. Чужие поля и подозрительные адреса отбрасываем."""
    if not isinstance(sub, dict):
        return False
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    if not (isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) < 1000):
        return False
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (isinstance(p256dh, str) and isinstance(auth, str) and len(p256dh) < 200 and len(auth) < 100):
        return False
    # Подписку другого человека перехватить нельзя: endpoint уникален, и при
    # повторной регистрации тем же браузером он просто переезжает к новому владельцу
    # (кто вошёл в аккаунт на этом устройстве последним, тот и получает).
    db.execute(
        """INSERT INTO push_subs (user_id, endpoint, p256dh, auth, device, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id,
               p256dh=excluded.p256dh, auth=excluded.auth, device=excluded.device, fails=0""",
        (user_id, endpoint, p256dh, auth, (device or "")[:80], int(time.time())))
    return True


def unsubscribe(user_id: int, endpoint: str) -> None:
    db.execute("DELETE FROM push_subs WHERE user_id=? AND endpoint=?", (user_id, endpoint))


def count(user_id: int) -> int:
    row = db.query_one("SELECT COUNT(*) n FROM push_subs WHERE user_id=?", (user_id,))
    return row["n"] if row else 0


def subs_of(user_id: int) -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM push_subs WHERE user_id=?", (user_id,))]


# ------------------------------------------------------------------ отправка
def _send_one(sub: dict, payload: str, ttl: int, urgency: str) -> str:
    """ok | gone | fail. Синхронная (requests внутри pywebpush) — зовём из потока."""
    _load()
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"],
                               "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=payload,
            vapid_private_key=_vapid,
            # pywebpush дописывает в словарь aud и exp — каждый раз новый
            vapid_claims={"sub": SITE_URL if SITE_URL.startswith("https") else "mailto:admin@tajscore.tj"},
            ttl=ttl, timeout=15, headers={"Urgency": urgency},
        )
        return "ok"
    except WebPushException as e:
        status = getattr(e.response, "status_code", None) if e.response is not None else None
        if status in (404, 410):
            return "gone"            # браузер отписался или удалил приложение
        log.warning("web-push %s: %s", status, str(e)[:160])
        return "fail"
    except Exception as e:
        log.warning("web-push: %s", type(e).__name__)
        return "fail"


async def send(user_id: int, title: str, body: str, url: str, tag: str,
               silent: bool = False, ttl: int = 1800, urgency: str = "high") -> int:
    """Шлёт на все устройства человека. Возвращает число доставленных."""
    subs = await asyncio.to_thread(subs_of, user_id)
    if not subs:
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag,
                          "silent": silent, "icon": "/static/img/icon-192.png",
                          "badge": "/static/img/icon-192.png"}, ensure_ascii=False)
    ok = 0
    for sub in subs:
        res = await asyncio.to_thread(_send_one, sub, payload, ttl, urgency)
        if res == "ok":
            ok += 1
            await asyncio.to_thread(db.execute,
                                    "UPDATE push_subs SET last_ok=?, fails=0 WHERE id=?",
                                    (int(time.time()), sub["id"]))
        elif res == "gone":
            await asyncio.to_thread(db.execute, "DELETE FROM push_subs WHERE id=?", (sub["id"],))
        else:
            # после десяти неудач подряд подписка считается мёртвой
            await asyncio.to_thread(db.execute,
                                    "UPDATE push_subs SET fails=fails+1 WHERE id=?", (sub["id"],))
            await asyncio.to_thread(db.execute,
                                    "DELETE FROM push_subs WHERE id=? AND fails>=10", (sub["id"],))
    return ok
