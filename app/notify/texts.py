"""Тексты уведомлений на трёх языках.

Каждое уведомление собирается в двух видах: HTML для Telegram и простой текст
(заголовок + тело) для web-push — системные уведомления разметку не понимают.
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import LEAGUE_BY_ID, SITE_URL

T = {
    "ru": {
        "reminder": "⏰ Через {mins} мин",
        "reminder_title": "Скоро матч",
        "lineups": "📋 Составы объявлены",
        "kickoff": "▶️ Матч начался",
        "goal": "⚽ ГОЛ!",
        "goal_cancelled": "❌ Гол отменён",
        "red_card": "🟥 Удаление",
        "halftime": "⏸ Перерыв",
        "fulltime": "🏁 Матч окончен",
        "postponed": "⚠️ Матч перенесён",
        "cancelled": "⚠️ Матч отменён",
        "abandoned": "⚠️ Матч прерван",
        "pens": "пен.",
        "open": "📊 Открыть матч",
        "mute": "🔕 Не уведомлять об этом матче",
        "test_title": "Tajscore: проверка",
        "test_body": "Уведомления работают! Так будут выглядеть голы и результаты ваших команд.",
        "winner": "Победа: {team}",
        "draw": "Ничья",
    },
    "tg": {
        "reminder": "⏰ Баъди {mins} дақ",
        "reminder_title": "Бозӣ наздик аст",
        "lineups": "📋 Таркибҳо эълон шуданд",
        "kickoff": "▶️ Бозӣ оғоз шуд",
        "goal": "⚽ ГОЛ!",
        "goal_cancelled": "❌ Гол бекор шуд",
        "red_card": "🟥 Кортчаи сурх",
        "halftime": "⏸ Танаффус",
        "fulltime": "🏁 Бозӣ анҷом ёфт",
        "postponed": "⚠️ Бозӣ мавқуф гузошта шуд",
        "cancelled": "⚠️ Бозӣ бекор шуд",
        "abandoned": "⚠️ Бозӣ қатъ шуд",
        "pens": "пен.",
        "open": "📊 Кушодани бозӣ",
        "mute": "🔕 Дар бораи ин бозӣ хабар надиҳед",
        "test_title": "Tajscore: санҷиш",
        "test_body": "Огоҳиномаҳо кор мекунанд! Голҳо ва натиҷаҳои дастаҳои шумо ҳамин тавр меоянд.",
        "winner": "Ғалаба: {team}",
        "draw": "Дуранг",
    },
    "en": {
        "reminder": "⏰ In {mins} min",
        "reminder_title": "Match starting soon",
        "lineups": "📋 Line-ups announced",
        "kickoff": "▶️ Kick-off",
        "goal": "⚽ GOAL!",
        "goal_cancelled": "❌ Goal disallowed",
        "red_card": "🟥 Red card",
        "halftime": "⏸ Half-time",
        "fulltime": "🏁 Full-time",
        "postponed": "⚠️ Match postponed",
        "cancelled": "⚠️ Match cancelled",
        "abandoned": "⚠️ Match abandoned",
        "pens": "pens",
        "open": "📊 Open match",
        "mute": "🔕 Mute this match",
        "test_title": "Tajscore: test",
        "test_body": "Notifications work! This is how goals and results of your teams will look.",
        "winner": "Winner: {team}",
        "draw": "Draw",
    },
}


def tr(lang: str, key: str, **kw) -> str:
    s = T.get(lang, T["ru"]).get(key) or T["ru"].get(key, key)
    return s.format(**kw) if kw else s


def team_name(team: dict, lang: str) -> str:
    return team.get({"ru": "name", "tg": "name_tg", "en": "name_en"}.get(lang, "name")) \
        or team.get("name") or "—"


def league_name(league_id: int, lang: str) -> str:
    cfg = LEAGUE_BY_ID.get(league_id) or {}
    return cfg.get(f"name_{lang}") or cfg.get("name_ru") or ""


def match_url(fixture_id: int) -> str:
    return f"{SITE_URL}/match/{fixture_id}"


def _time(ts: int, tz: str) -> str:
    try:
        return datetime.fromtimestamp(ts, ZoneInfo(tz)).strftime("%H:%M")
    except Exception:
        return datetime.utcfromtimestamp(ts).strftime("%H:%M")


def _minute(ev: dict) -> str:
    m = ev.get("minute")
    if m is None:
        return ""
    extra = ev.get("extra")
    return f" {m}+{extra}'" if extra else f" {m}'"


def build(ev: dict, lang: str, tz: str) -> dict:
    """ev — событие из engine: kind, fixture (dict), side, minute, ...
    Возвращает {"html": ..., "title": ..., "body": ...}."""
    f = ev["fixture"]
    kind = ev["kind"]
    home, away = team_name(f["home"], lang), team_name(f["away"], lang)
    hg, ag = f["goals"]["home"], f["goals"]["away"]
    league = league_name(f["league_id"], lang)
    e = html.escape

    score_html = f"{e(home)} <b>{hg if hg is not None else 0}:{ag if ag is not None else 0}</b> {e(away)}"
    score_txt = f"{home} {hg if hg is not None else 0}:{ag if ag is not None else 0} {away}"
    pair_html = f"<b>{e(home)}</b> — <b>{e(away)}</b>"
    pair_txt = f"{home} — {away}"

    if kind == "reminder":
        head = tr(lang, "reminder", mins=ev.get("mins", 15))
        line = f"{pair_html}\n🕒 {_time(f['timestamp'], tz)}"
        title, body = tr(lang, "reminder_title"), f"{pair_txt} · {_time(f['timestamp'], tz)}"
    elif kind == "kickoff":
        head, line = tr(lang, "kickoff"), pair_html
        title, body = tr(lang, "kickoff"), pair_txt
    elif kind == "goal":
        scorer_side = home if ev.get("side") == "home" else away
        who = ev.get("scorer")
        head = f"{tr(lang, 'goal')}{_minute(ev)}"
        # счёт забившей стороны выделяем: с первого взгляда видно, кто забил
        if ev.get("side") == "home":
            line = f"<b>{e(home)} {hg}</b>:{ag} {e(away)}"
        else:
            line = f"{e(home)} {hg}:<b>{ag} {e(away)}</b>"
        if who:
            line += f"\n👟 {e(who)}"
        title = f"{tr(lang, 'goal')}{_minute(ev)} {scorer_side}"
        body = score_txt + (f" · {who}" if who else "")
    elif kind == "goal_cancelled":
        head, line = tr(lang, "goal_cancelled"), score_html
        title, body = tr(lang, "goal_cancelled"), score_txt
    elif kind == "red_card":
        side_name = home if ev.get("side") == "home" else away
        who = ev.get("player")
        head = f"{tr(lang, 'red_card')}{_minute(ev)} · {e(side_name)}"
        line = score_html + (f"\n👤 {e(who)}" if who else "")
        title, body = f"{tr(lang, 'red_card')} · {side_name}", score_txt + (f" · {who}" if who else "")
    elif kind == "lineups":
        head, line = tr(lang, "lineups"), pair_html
        title, body = tr(lang, "lineups"), pair_txt
    elif kind == "halftime":
        head, line = tr(lang, "halftime"), score_html
        title, body = tr(lang, "halftime"), score_txt
    elif kind == "fulltime":
        extra = ""
        pen = f.get("pen") or {}
        if pen.get("home") is not None and pen.get("away") is not None:
            extra = f" ({tr(lang, 'pens')} {pen['home']}:{pen['away']})"
        winner = f.get("winner")
        res = tr(lang, "draw") if winner == "draw" else (
            tr(lang, "winner", team=home if winner == "home" else away) if winner else "")
        head = tr(lang, "fulltime")
        line = score_html + e(extra) + (f"\n{e(res)}" if res else "")
        title, body = tr(lang, "fulltime"), score_txt + extra
    elif kind == "postponed":
        key = {"CANC": "cancelled", "ABD": "abandoned"}.get(f.get("status"), "postponed")
        head, line = tr(lang, key), pair_html
        title, body = tr(lang, key), pair_txt
    else:
        head, line, title, body = kind, pair_html, kind, pair_txt

    league_line = f"\n🏆 {e(league)}" if league else ""
    return {
        "html": f"<b>{head}</b>\n{line}{league_line}",
        "title": title,
        "body": body + (f" · {league}" if league else ""),
    }
