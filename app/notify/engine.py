"""Движок уведомлений: замечает события в матчах и рассылает их подписчикам.

Как рождается уведомление. Оба воркера синхронизации пишут в таблицу fixtures
свежий счёт и статус. Раз в несколько секунд движок сравнивает каждый
ближайший матч с его прошлым снимком (notify_state):

    был NS, стал 1H           -> «Матч начался»
    было 0:0, стало 1:0        -> «ГОЛ!»
    было 1:0, стало 0:0        -> «Гол отменён»
    стал HT / FT / PST         -> перерыв / итог / перенос
    в событиях новая красная   -> «Удаление»
    появились составы          -> «Составы объявлены»

Плюс раз в минуту — напоминания за N минут до начала (N выбирает человек).

Кому. Подписчики матча — люди, у которых в избранном сам матч, одна из двух
команд или его лига. Для каждого вида избранного своя подробность (все
события / только ключевые / ничего), см. app/notify/prefs.py.

Дубли. Каждая отправка записывается в notify_sent с ключом вида «goal:2-1»;
повторный опрос, рестарт сервиса или два источника одного матча второго
сообщения не дадут.
"""
import asyncio
import logging
import time

from app import auth, db, teams_tj
from app.notify import prefs as P
from app.notify import telegram as tg
from app.notify import texts, webpush
from app.services.common import FIXTURE_SELECT, fixture_row

log = logging.getLogger("tajscore.notify")

LIVE = ("1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE")
FINISHED = ("FT", "AET", "PEN")
OFF = ("PST", "CANC", "ABD")
NOT_STARTED = ("NS", "TBD")

DETECT_EVERY = 5
REMIND_EVERY = 60
CLEANUP_EVERY = 3600

_queue: asyncio.Queue | None = None
_stats = {"sent_tg": 0, "sent_push": 0, "events": 0, "started": 0}


# ================================================================== подписчики
_team_favs_cache: dict = {"at": 0.0, "rows": []}


def _team_favs() -> list[tuple[int, int, str]]:
    """(user_id, team_id, русское имя) для всех избранных команд.

    Один клуб может жить в базе под двумя id (API-Football и football-data),
    поэтому подписку на команду сверяем ещё и по русскому названию — иначе
    болельщик «Реала» не узнал бы о голах в Лиге чемпионов.
    """
    now = time.monotonic()
    if now - _team_favs_cache["at"] < 30:
        return _team_favs_cache["rows"]
    rows = db.query(
        """SELECT f.user_id, f.item_id, t.name FROM favorites f
           JOIN users u ON u.id = f.user_id
           LEFT JOIN teams t ON t.id = f.item_id
           WHERE f.type='team' AND u.notifications_enabled=1""")
    out = [(r["user_id"], r["item_id"], teams_tj.names(r["item_id"], r["name"])[0]) for r in rows]
    _team_favs_cache.update(at=now, rows=out)
    return out


_RANK = {"all": 2, "key": 1, "off": 0}


def subscribers(fx: dict) -> list[tuple[dict, dict, str]]:
    """[(пользователь, настройки, уровень)] для матча."""
    fid, lid = fx["id"], fx["league_id"]
    hid, aid = fx["home"]["id"], fx["away"]["id"]
    hname, aname = fx["home"]["name"], fx["away"]["name"]

    hits: dict[int, set[str]] = {}
    for r in db.query(
            """SELECT f.user_id, f.type FROM favorites f JOIN users u ON u.id = f.user_id
               WHERE u.notifications_enabled=1 AND (
                   (f.type='match' AND f.item_id=?) OR (f.type='league' AND f.item_id=?))""",
            (fid, lid)):
        hits.setdefault(r["user_id"], set()).add(r["type"])
    for uid, tid, ru in _team_favs():
        if tid in (hid, aid) or (ru and ru in (hname, aname)):
            hits.setdefault(uid, set()).add("team")
    if not hits:
        return []

    ids = list(hits)
    muted = {r["user_id"] for r in db.query(
        f"SELECT user_id FROM notify_mutes WHERE fixture_id=? AND user_id IN ({','.join('?' * len(ids))})",
        (fid, *ids))}
    users = {r["id"]: dict(r) for r in db.query(
        f"SELECT * FROM users WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))}
    prefs = P.load_many(ids)

    out = []
    src_key = {"match": "matches", "team": "teams", "league": "leagues"}
    for uid, kinds in hits.items():
        if uid in muted or uid not in users:
            continue
        pr = prefs[uid]
        level = max((pr["sources"][src_key[k]] for k in kinds), key=lambda lv: _RANK[lv])
        if level != "off":
            out.append((users[uid], pr, level))
    return out


# ================================================================== обнаружение
def _snapshots(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in db.query(
                f"SELECT * FROM notify_state WHERE fixture_id IN ({','.join('?' * len(part))})",
                tuple(part)):
            out[r["fixture_id"]] = dict(r)
    return out


def _reds_and_lineups(ids: list[int]) -> tuple[dict, dict]:
    """Красные карточки по командам и наличие составов — из карточек матчей.
    Есть только у матчей, для которых API-Football отдал события."""
    reds: dict[tuple[int, int], int] = {}
    lineups: dict[int, int] = {}
    if not ids:
        return reds, lineups
    q = ",".join("?" * len(ids))
    for r in db.query(
            f"""SELECT fixture_id, team_id, COUNT(*) n FROM fixture_events
                WHERE fixture_id IN ({q}) AND type='Card'
                  AND detail IN ('Red Card', 'Second Yellow card')
                GROUP BY fixture_id, team_id""", tuple(ids)):
        reds[(r["fixture_id"], r["team_id"])] = r["n"]
    for r in db.query(
            f"SELECT fixture_id, COUNT(*) n FROM fixture_players WHERE fixture_id IN ({q}) GROUP BY fixture_id",
            tuple(ids)):
        lineups[r["fixture_id"]] = 1 if r["n"] else 0
    return reds, lineups


def _last_event(fixture_id: int, team_id: int, kind: str) -> dict | None:
    if kind == "goal":
        cond = "type='Goal' AND detail <> 'Missed Penalty'"
    else:
        cond = "type='Card' AND detail IN ('Red Card', 'Second Yellow card')"
    r = db.query_one(
        f"""SELECT minute, extra, player_name FROM fixture_events
            WHERE fixture_id=? AND team_id=? AND {cond}
            ORDER BY minute DESC, extra DESC, idx DESC LIMIT 1""", (fixture_id, team_id))
    return dict(r) if r else None


def detect() -> list[dict]:
    """Сравнивает матчи со снимками и возвращает новые события. Синхронная —
    вызывается в потоке, чтобы не держать цикл сайта."""
    now = int(time.time())
    rows = db.query(f"{FIXTURE_SELECT} WHERE f.timestamp BETWEEN ? AND ?",
                    (now - 6 * 3600, now + 2 * 86400))
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    snaps = _snapshots(ids)
    reds, lineups = _reds_and_lineups(ids)
    events: list[dict] = []
    updates = []

    for r in rows:
        fid = r["id"]
        st = r["status_short"] or "NS"
        hg, ag = r["home_goals"], r["away_goals"]
        cur = {
            "status": st, "home": hg, "away": ag,
            "red_home": reds.get((fid, r["home_id"]), 0),
            "red_away": reds.get((fid, r["away_id"]), 0),
            "lineups": lineups.get(fid, 0),
        }
        snap = snaps.get(fid)
        if snap is not None and all(snap.get(k) == v for k, v in cur.items()):
            continue
        updates.append((fid, st, hg, ag, cur["red_home"], cur["red_away"], cur["lineups"], now))
        if snap is None:
            continue           # первый взгляд на матч — запоминаем, не шлём

        fx = None

        def add(kind, **kw):
            nonlocal fx
            if fx is None:
                fx = fixture_row(r)
            events.append({"kind": kind, "fixture": fx, **kw})

        prev = snap["status"] or "NS"
        recent = now - (r["timestamp"] or 0) < 4 * 3600   # не будим людей вчерашним

        if prev in NOT_STARTED and st in LIVE and recent:
            add("kickoff", key="kickoff")

        # Голы. Пустой счёт до начала считаем 0:0, чтобы гол на 1-й минуте не потерялся.
        ph = snap["home"] if snap["home"] is not None else (0 if prev in NOT_STARTED else None)
        pa = snap["away"] if snap["away"] is not None else (0 if prev in NOT_STARTED else None)
        if hg is not None and ag is not None and ph is not None and pa is not None and recent \
                and (st in LIVE or st in FINISHED):
            if hg > ph or ag > pa:
                for side, new, old, tid in (("home", hg, ph, r["home_id"]), ("away", ag, pa, r["away_id"])):
                    if new > old:
                        last = _last_event(fid, tid, "goal") or {}
                        add("goal", key=f"goal:{hg}-{ag}:{side}", side=side,
                            minute=last.get("minute") or r["elapsed"],
                            extra=last.get("extra") if last else r["extra_minute"],
                            scorer=last.get("player_name"))
            elif hg < ph or ag < pa:
                add("goal_cancelled", key=f"cancel:{hg}-{ag}")
                # гол отменили — следующий настоящий гол может дать тот же счёт,
                # и о нём тоже надо сообщить: забываем, что о голах уже писали
                db.execute("DELETE FROM notify_sent WHERE fixture_id=? AND kind LIKE 'goal:%'", (fid,))

        if st == "HT" and prev != "HT" and recent:
            add("halftime", key="halftime")
        if st in FINISHED and prev not in FINISHED and recent:
            add("fulltime", key="fulltime")
        if st in OFF and prev != st:
            add("postponed", key=f"off:{st}")
        if recent:
            for side, n, old, tid in (("home", cur["red_home"], snap["red_home"], r["home_id"]),
                                      ("away", cur["red_away"], snap["red_away"], r["away_id"])):
                if n > (old or 0):
                    last = _last_event(fid, tid, "red") or {}
                    add("red_card", key=f"red:{side}:{n}", side=side,
                        minute=last.get("minute"), extra=last.get("extra"),
                        player=last.get("player_name"))
        if cur["lineups"] and not snap["lineups"] and st in NOT_STARTED:
            add("lineups", key="lineups")

    if updates:
        db.executemany(
            """INSERT INTO notify_state (fixture_id, status, home, away, red_home, red_away, lineups, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(fixture_id) DO UPDATE SET status=excluded.status, home=excluded.home,
                   away=excluded.away, red_home=excluded.red_home, red_away=excluded.red_away,
                   lineups=excluded.lineups, updated_at=excluded.updated_at""", updates)
    return events


def reminders() -> list[dict]:
    """Матчи, которые начнутся в ближайшие 2 часа: каждому подписчику —
    в своё время (за 5/15/30/60/120 минут, как он выбрал)."""
    now = int(time.time())
    rows = db.query(
        f"""{FIXTURE_SELECT} WHERE f.timestamp > ? AND f.timestamp <= ?
            AND f.status_short IN ('NS', 'TBD')""", (now, now + 121 * 60))
    return [{"kind": "reminder", "key": "reminder", "fixture": fixture_row(r)} for r in rows]


# ================================================================== рассылка
def _claim(user_id: int, fixture_id: int, key: str) -> bool:
    """Первая попытка отправить это событие этому человеку? Атомарно."""
    cur = db.execute(
        "INSERT OR IGNORE INTO notify_sent (user_id, fixture_id, kind, sent_at) VALUES (?,?,?,?)",
        (user_id, fixture_id, key, int(time.time())))
    return bool(cur and cur.rowcount)


def plan(ev: dict) -> list[dict]:
    """Событие -> список заданий на отправку конкретным людям."""
    fx = ev["fixture"]
    kind = ev["kind"]
    jobs = []
    now = int(time.time())
    for user, pr, level in subscribers(fx):
        if not pr["events"].get(kind) or not P.level_allows(level, kind):
            continue
        if kind == "reminder":
            left = fx["timestamp"] - now
            if left > pr["reminder_min"] * 60:
                continue          # ещё рано для этого человека
            ev = {**ev, "mins": max(1, round(left / 60))}
        quiet = P.in_quiet_hours(pr)
        if quiet and pr["quiet"]["mode"] == "skip":
            continue
        if not _claim(user["id"], fx["id"], ev["key"]):
            continue
        jobs.append({"user": user, "prefs": pr, "event": ev, "silent": quiet})
    return jobs


async def deliver(job: dict) -> None:
    user, pr, ev = job["user"], job["prefs"], job["event"]
    lang = pr["lang"]
    msg = texts.build(ev, lang, pr["tz"])
    fx = ev["fixture"]
    url = texts.match_url(fx["id"])

    if pr["channels"]["telegram"] and not user.get("is_blocked"):
        try:
            if await tg.send_message(
                    user["telegram_id"], msg["html"],
                    tg.match_buttons(url, fx["id"], texts.tr(lang, "open"), texts.tr(lang, "mute")),
                    silent=job["silent"]):
                _stats["sent_tg"] += 1
        except tg.Blocked:
            await asyncio.to_thread(auth.mark_blocked, user["telegram_id"], True)
    if pr["channels"]["push"]:
        # tag = матч: новое уведомление по матчу заменяет старое, а не копится стопкой
        n = await webpush.send(user["id"], msg["title"], msg["body"], url,
                               tag=f"m{fx['id']}", silent=job["silent"],
                               urgency="normal" if ev["kind"] == "reminder" else "high")
        _stats["sent_push"] += n


async def send_test(user: dict) -> dict:
    """Кнопка «Проверить» в настройках: по одному сообщению в каждый канал."""
    pr = await asyncio.to_thread(P.load, user["id"])
    lang = pr["lang"]
    out = {"telegram": False, "push": 0}
    if pr["channels"]["telegram"] and user.get("telegram_id"):
        try:
            out["telegram"] = await tg.send_message(
                user["telegram_id"],
                f"🔔 <b>{texts.tr(lang, 'test_title')}</b>\n{texts.tr(lang, 'test_body')}")
            if out["telegram"] and user.get("is_blocked"):
                await asyncio.to_thread(auth.mark_blocked, user["telegram_id"], False)
        except tg.Blocked:
            await asyncio.to_thread(auth.mark_blocked, user["telegram_id"], True)
    if pr["channels"]["push"]:
        out["push"] = await webpush.send(user["id"], texts.tr(lang, "test_title"),
                                         texts.tr(lang, "test_body"),
                                         texts.SITE_URL + "/", tag="test")
    return out


# ================================================================== циклы
async def _producer() -> None:
    last_remind = last_clean = 0.0
    while True:
        try:
            events = await asyncio.to_thread(detect)
            now = time.monotonic()
            if now - last_remind >= REMIND_EVERY:
                last_remind = now
                events += await asyncio.to_thread(reminders)
            for ev in events:
                jobs = await asyncio.to_thread(plan, ev)
                if ev["kind"] != "reminder" or jobs:
                    _stats["events"] += 1
                for j in jobs:
                    await _queue.put(j)
            if now - last_clean >= CLEANUP_EVERY:
                last_clean = now
                await asyncio.to_thread(cleanup)
                from app import backup
                await backup.run_if_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("ошибка в цикле уведомлений")
        await asyncio.sleep(DETECT_EVERY)


async def _consumer() -> None:
    while True:
        job = await _queue.get()
        try:
            await deliver(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("не удалось доставить уведомление")
        finally:
            _queue.task_done()


def cleanup() -> None:
    now = int(time.time())
    db.execute("DELETE FROM notify_sent WHERE sent_at < ?", (now - 14 * 86400,))
    db.execute("DELETE FROM notify_state WHERE updated_at < ?", (now - 3 * 86400,))
    db.execute("DELETE FROM notify_mutes WHERE created_at < ?", (now - 30 * 86400,))


def stats() -> dict:
    day = int(time.time()) - 86400
    row = db.query_one("SELECT COUNT(*) n FROM notify_sent WHERE sent_at >= ?", (day,))
    subs = db.query_one("SELECT COUNT(*) n FROM push_subs")
    return {**_stats, "queue": _queue.qsize() if _queue else 0,
            "sent_24h": row["n"] if row else 0, "push_devices": subs["n"] if subs else 0}


async def run_forever() -> None:
    global _queue
    _queue = asyncio.Queue(maxsize=50_000)
    _stats["started"] = int(time.time())
    log.info("Уведомления: движок запущен")
    tasks = [asyncio.create_task(_producer(), name="notify-producer"),
             asyncio.create_task(_consumer(), name="notify-consumer")]
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        await tg.close()
