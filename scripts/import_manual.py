"""Импорт лиги из файла — для турниров, которых нет ни в одном бесплатном API
(Лигаи Олӣ и т.п.).

Запуск:  ./venv/bin/python scripts/import_manual.py data/tjk.json

Формат файла:
{
  "league_id": 571,
  "season": 2026,
  "teams": ["Истиклол", "Худжанд", "Регар-ТадАЗ"],
  "matches": [
    {"date": "2026-09-13 18:00", "home": "Истиклол", "away": "Худжанд", "score": "2:1"},
    {"date": "2026-09-20 17:00", "home": "Регар-ТадАЗ", "away": "Истиклол"}
  ]
}

teams  — необязателен: команды и так заводятся из матчей, но список нужен,
         если кто-то ещё не сыграл ни одного матча.
score  — необязателен: без него матч считается будущим (статус NS).
date   — местное время Душанбе (UTC+5), формат «ГГГГ-ММ-ДД ЧЧ:ММ».
Повторный запуск обновляет уже загруженное, дублей не создаёт.
"""
import json
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import analytics, db
from app.sync.fdorg import TEAM_OFFSET, normalize

MANUAL_FIXTURE_OFFSET = 950_000_000
TZ = timezone(timedelta(hours=5))   # Asia/Dushanbe

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(1)

src = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
league_id = int(src["league_id"])
season = int(src.get("season") or 2026)

db.init_db()
idx = {normalize(r["name"]): r["id"] for r in db.query("SELECT id, name FROM teams")}
next_id = (db.query_one("SELECT MAX(id) m FROM teams WHERE id >= ?", (TEAM_OFFSET,))["m"]
           or TEAM_OFFSET) + 1


def team_id(conn, name: str) -> int:
    """Ищет команду по имени, при отсутствии заводит новую."""
    global next_id
    key = normalize(name)
    if key in idx:
        return idx[key]
    tid = next_id
    next_id += 1
    conn.execute("INSERT INTO teams (id, name) VALUES (?,?)", (tid, name.strip()))
    idx[key] = tid
    return tid


now = int(time.time())
added_t = added_m = 0
with db.write() as conn:
    for name in src.get("teams") or []:
        before = len(idx)
        team_id(conn, name)
        added_t += len(idx) - before

    for i, m in enumerate(src.get("matches") or []):
        hid, aid = team_id(conn, m["home"]), team_id(conn, m["away"])
        dt = datetime.strptime(m["date"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        ts = int(dt.timestamp())
        gh = ga = None
        if m.get("score"):
            gh, ga = [int(x) for x in str(m["score"]).replace("-", ":").split(":")]
        st = "FT" if gh is not None else "NS"
        winner = None if gh is None else ("home" if gh > ga else "away" if ga > gh else "draw")

        row = db.query_one(
            """SELECT id FROM fixtures WHERE league_id=? AND home_id=? AND away_id=?
               AND ABS(timestamp - ?) < 86400""", (league_id, hid, aid, ts))
        fid = row["id"] if row else MANUAL_FIXTURE_OFFSET + league_id * 1000 + i

        conn.execute(
            """INSERT INTO fixtures (id, league_id, season, round, date_utc, timestamp,
                    status_short, status_long, home_id, away_id, home_goals, away_goals,
                    ft_home, ft_away, winner, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                    date_utc=excluded.date_utc, timestamp=excluded.timestamp,
                    status_short=excluded.status_short, home_goals=excluded.home_goals,
                    away_goals=excluded.away_goals, ft_home=excluded.ft_home,
                    ft_away=excluded.ft_away, winner=excluded.winner,
                    updated_at=excluded.updated_at""",
            (fid, league_id, season, m.get("round") or "", dt.astimezone(timezone.utc)
             .strftime("%Y-%m-%dT%H:%M:%S+00:00"), ts, st,
             "Match Finished" if gh is not None else "Not Started",
             hid, aid, gh, ga, gh, ga, winner, now))
        added_m += 1

print(f"Команд добавлено: {added_t}")
print(f"Матчей записано:  {added_m}")
analytics.recompute_all(league_id)
st = db.query_one("SELECT COUNT(*) n FROM standings WHERE league_id=?", (league_id,))["n"]
print(f"Строк в таблице:  {st}")
