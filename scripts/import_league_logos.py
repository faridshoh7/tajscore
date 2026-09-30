"""Берёт logo/flag лиг из data/leagues_raw.json (скачан один раз) и пишет в БД."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import db
from app.config import LEAGUE_BY_ID, ROOT

raw = json.loads((ROOT / "data" / "leagues_raw.json").read_text())["response"]
n = 0
with db.write() as conn:
    for it in raw:
        lid = it["league"]["id"]
        if lid not in LEAGUE_BY_ID:
            continue
        conn.execute("UPDATE leagues SET logo=?, flag=?, country=? WHERE id=?",
                     (it["league"]["logo"], it["country"]["flag"], it["country"]["name"], lid))
        n += 1
print(f"Обновлено лиг (лого/флаг): {n}")
for r in db.query("SELECT id,name_ru,logo,flag FROM leagues ORDER BY priority LIMIT 4"):
    print(" ", r["id"], r["name_ru"], "|", r["logo"], "|", r["flag"])
