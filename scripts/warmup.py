"""Первичная заливка: расписание на 3 дня + таблицы приоритетных лиг.

Запуск:  ./venv/bin/python scripts/warmup.py [сколько_запросов_максимум]
Осторожно: тратит дневной лимит. По умолчанию не больше 8 запросов.
"""
import asyncio, logging, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app import budget, db
from app.api_client import api
from app.config import USE_API_STANDINGS
from app.sync import tasks

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 8


async def main():
    db.init_db()
    spent_before = budget.used_today()
    plan = [("расписание сегодня", tasks.sync_fixtures_date(tasks.utc_date(0), "fixtures_today")),
            ("расписание завтра",  tasks.sync_fixtures_date(tasks.utc_date(1), "fixtures_around")),
            ("расписание вчера",   tasks.sync_fixtures_date(tasks.utc_date(-1), "fixtures_around")),
            ("live-матчи",         tasks.sync_live())]
    # На free-тарифе /standings закрыт для текущего сезона: запрос всё равно спишется
    # с дневной квоты и вернёт ошибку plan. Таблицы считает analytics.recompute_all().
    if USE_API_STANDINGS:
        for lid in (571, 39, 2, 140):
            plan.append((f"таблица лиги {lid}", tasks.sync_standings(lid)))
    else:
        print("Тариф free: таблицы из API не тянем, считаем локально из матчей")

    for i, (label, coro) in enumerate(plan):
        if budget.used_today() - spent_before >= MAX:
            coro.close()
            print(f"[стоп] достигнут лимит прогрева ({MAX} запросов)")
            break
        print(f"→ {label} ...")
        try:
            print("   результат:", await coro)
        except Exception as e:
            print("   ошибка:", e)
    await api.close()
    print("\nБюджет:", budget.stats())
    print("Матчей в базе:", db.query_one("SELECT COUNT(*) n FROM fixtures")["n"])
    print("Команд в базе:", db.query_one("SELECT COUNT(*) n FROM teams")["n"])

asyncio.run(main())
