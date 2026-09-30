"""Создать/обновить структуру БД и справочник лиг."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import db

db.init_db()
rows = db.query("SELECT id, name_ru, country_ru, season, priority FROM leagues ORDER BY priority")
print(f"БД готова: {db.DB_PATH if hasattr(db,'DB_PATH') else ''}")
print(f"Лиг в справочнике: {len(rows)}")
for r in rows:
    print("  %-5s %-30s %-22s сезон %s" % (r["id"], r["name_ru"], r["country_ru"], r["season"]))
