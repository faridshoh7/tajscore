"""Разовый импорт полного сезона из football-data.org.

Запуск:  ./venv/bin/python scripts/import_fdorg.py [id_лиги ...]
Без аргументов — все покрытые лиги. Дневную квоту API-Football не тратит:
это другой источник со своим ключом (FOOTBALL_DATA_KEY в .env).

В обычной работе то же самое делает воркер сам; скрипт нужен, чтобы быстро
прогреть базу с нуля, не дожидаясь обхода по расписанию. Паузы между запросами
держит сам клиент — у него скользящий ограничитель на 10 запросов в минуту.
"""
import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app import analytics, db
from app.config import FD_KEY
from app.sync import fdorg
from app.sync.fd_client import fd

ids = [int(a) for a in sys.argv[1:]] or list(fdorg.COMPETITIONS)


async def main() -> None:
    db.init_db()
    if not FD_KEY:
        print("Нет ключа. Добавь в .env строку:  FOOTBALL_DATA_KEY=твой_ключ")
        raise SystemExit(1)

    total_m = total_t = total_s = total_st = 0
    try:
        for lid in ids:
            name = db.query_one("SELECT name_ru FROM leagues WHERE id=?", (lid,))
            label = name["name_ru"] if name else lid
            print(f"\n→ {label} (id {lid})")
            t = await fdorg.import_teams(lid)
            m = await fdorg.import_matches(lid)
            st = await fdorg.import_standings(lid)
            sc = await fdorg.import_scorers(lid)
            print(f"   команд: {t}, матчей: {m}, строк таблицы: {st}, "
                  f"бомбардиров: {sc.get('goals', 0)}")
            total_t += t
            total_m += m
            total_st += st
            total_s += sc.get("goals", 0)
    finally:
        await fd.close()

    print(f"\nВсего: команд {total_t}, матчей {total_m}, "
          f"строк таблиц {total_st}, бомбардиров {total_s}")
    print("Пересчитываю статистику…")
    analytics.recompute_all()
    print("Матчей в базе:", db.query_one("SELECT COUNT(*) n FROM fixtures")["n"])
    print("Команд в базе:", db.query_one("SELECT COUNT(*) n FROM teams")["n"])


asyncio.run(main())
