"""Разведка: что именно доступно на бесплатном тарифе. Тратит ~4 запроса."""
import asyncio, pathlib, sys, logging
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.ERROR)
from app.api_client import api
from app import budget

CHECKS = [
    ("Таблица АПЛ, сезон 2026",        "/standings", {"league": 39, "season": 2026}),
    ("Все матчи АПЛ за сезон 2026",    "/fixtures",  {"league": 39, "season": 2026}),
    ("Таблица АПЛ, сезон 2024",        "/standings", {"league": 39, "season": 2024}),
    ("Бомбардиры АПЛ, сезон 2026",     "/players/topscorers", {"league": 39, "season": 2026}),
]

async def main():
    for label, ep, params in CHECKS:
        try:
            r = await api.get(ep, params, "probe", force=True)
            print(f"{'ДОСТУПНО ' if r else 'ЗАКРЫТО  '} {label}: {len(r) if r is not None else '—'} записей")
        except Exception as e:
            print(f"ЗАКРЫТО   {label}: {e}")
    await api.close()
    print("\nПотрачено сегодня:", budget.used_today())

asyncio.run(main())
