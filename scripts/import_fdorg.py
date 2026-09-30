"""Импорт полного сезона из football-data.org.

Запуск:  ./venv/bin/python scripts/import_fdorg.py [id_лиги ...]
Без аргументов — все покрытые лиги. Дневную квоту API-Football не тратит:
это другой источник со своим ключом (FOOTBALL_DATA_KEY в .env).
"""
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app import analytics, db
from app.sync import fdorg

ids = [int(a) for a in sys.argv[1:]] or list(fdorg.COMPETITIONS)

db.init_db()
if not fdorg.KEY:
    print("Нет ключа. Добавь в .env строку:  FOOTBALL_DATA_KEY=твой_ключ")
    raise SystemExit(1)

total_m = total_t = total_s = 0
for lid in ids:
    name = db.query_one("SELECT name_ru FROM leagues WHERE id=?", (lid,))
    label = name["name_ru"] if name else lid
    print(f"\n→ {label} (id {lid})")
    t = fdorg.import_teams(lid)
    time.sleep(6)          # бесплатный тариф: не больше 10 запросов в минуту
    m = fdorg.import_matches(lid)
    time.sleep(6)
    sc = fdorg.import_scorers(lid)
    time.sleep(6)
    print(f"   команд: {t}, матчей: {m}, бомбардиров: {sc.get('goals', 0)}")
    total_t += t
    total_m += m
    total_s += sc.get("goals", 0)

print(f"\nВсего: команд {total_t}, матчей {total_m}, бомбардиров {total_s}")
print("Пересчитываю таблицы и статистику…")
analytics.recompute_all()
print("Матчей в базе:", db.query_one("SELECT COUNT(*) n FROM fixtures")["n"])
print("Команд в базе:", db.query_one("SELECT COUNT(*) n FROM teams")["n"])
