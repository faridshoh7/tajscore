"""Добор прошедших дат сезона. Запуск: ./venv/bin/python scripts/backfill.py [сколько_дней]"""
import asyncio, logging, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.WARNING)
from app import analytics, budget, db
from app.api_client import api
from app.sync import tasks

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10


async def main():
    done = 0
    while done < N:
        if not budget.can_spend("fixtures_backfill"):
            print("Бюджет исчерпан, останавливаюсь"); break
        d = tasks.backfill_next_date()
        if d is None:
            print("История собрана полностью"); break
        n = await tasks.sync_fixtures_date(d, "fixtures_backfill")
        if n < 0:
            print(f"{d}: ошибка, стоп"); break
        print(f"{d}: +{n} матчей")
        done += 1
    await api.close()
    analytics.recompute_all()
    print("\nПрогресс истории:", tasks.backfill_progress())
    print("Бюджет:", budget.stats())
    print("Матчей в базе:", db.query_one("SELECT COUNT(*) n FROM fixtures")["n"])

asyncio.run(main())
