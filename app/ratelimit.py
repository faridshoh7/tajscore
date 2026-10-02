"""Ограничение частоты запросов и защита админки от подбора пароля.

Счётчики живут в памяти процесса: сайт работает одним процессом uvicorn,
поэтому общий Redis не нужен. После рестарта счётчики обнуляются — для
защиты от скриптов этого достаточно.

Окно скользящее: храним отметки времени последних запросов и отбрасываем
те, что старше окна.
"""
import threading
import time
from collections import deque

from starlette.requests import Request

# (префикс пути, лимит, окно в секундах). Берётся первое совпадение.
RULES = [
    ("/api/search", 40, 60),
    ("/api/auth/start", 10, 60),
    ("/api/auth/poll", 90, 60),
    ("/api/favorites", 60, 60),
    ("/api/notify", 40, 60),
    ("/api/push", 20, 60),
    ("/api/", 300, 60),
    ("/adminpanel", 60, 60),
]

_hits: dict[tuple[str, str], deque] = {}
_lock = threading.Lock()
_last_gc = 0.0


def client_ip(request: Request) -> str:
    """Настоящий IP посетителя. Сайт стоит за nginx на той же машине, поэтому
    заголовку X-Real-IP верим только когда запрос пришёл с localhost —
    иначе любой подставил бы туда чужой адрес и обошёл лимит."""
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1"):
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return peer or "unknown"


def _rule(path: str):
    for prefix, limit, window in RULES:
        if path.startswith(prefix):
            return prefix, limit, window
    return None


def _gc(now: float) -> None:
    global _last_gc
    if now - _last_gc < 300:
        return
    _last_gc = now
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > 600]:
        _hits.pop(key, None)


def check(request: Request) -> int:
    """0 — пропускаем, иначе через сколько секунд можно повторить."""
    rule = _rule(request.url.path)
    if not rule:
        return 0
    prefix, limit, window = rule
    key = (prefix, client_ip(request))
    now = time.monotonic()
    with _lock:
        _gc(now)
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window - (now - q[0])) + 1)
        q.append(now)
    return 0


# ------------------------------------------------------------------ админка
# После MAX_FAILS неверных паролей за FAIL_WINDOW адрес блокируется на LOCKOUT.
MAX_FAILS = 5
FAIL_WINDOW = 15 * 60
LOCKOUT = 30 * 60

_fails: dict[str, deque] = {}
_locked_until: dict[str, float] = {}


def admin_locked(ip: str) -> int:
    """Сколько секунд ещё действует блокировка (0 — не заблокирован)."""
    with _lock:
        until = _locked_until.get(ip, 0)
        left = int(until - time.monotonic())
        if left <= 0:
            _locked_until.pop(ip, None)
            return 0
        return left


def admin_failed(ip: str) -> bool:
    """Отмечает неудачную попытку. True — адрес только что заблокирован."""
    now = time.monotonic()
    with _lock:
        q = _fails.setdefault(ip, deque())
        while q and now - q[0] > FAIL_WINDOW:
            q.popleft()
        q.append(now)
        if len(q) >= MAX_FAILS:
            _locked_until[ip] = now + LOCKOUT
            q.clear()
            return True
    return False


def admin_ok(ip: str) -> None:
    with _lock:
        _fails.pop(ip, None)
