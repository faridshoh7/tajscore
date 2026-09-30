"""Разовый скрипт: тянет ВЕСЬ справочник лиг API-Football одним запросом
и кладёт сырой JSON в data/leagues_raw.json. Плюс показывает остаток квоты."""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import httpx
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
KEY = os.environ["API_FOOTBALL_KEY"]
H = {"x-apisports-key": KEY}
BASE = "https://v3.football.api-sports.io"

with httpx.Client(timeout=60, headers=H) as c:
    st = c.get(f"{BASE}/status").json()
    print("Аккаунт:", json.dumps(st.get("response", {}), ensure_ascii=False))
    r = c.get(f"{BASE}/leagues")
    data = r.json()
    print("Лимит после запроса:", r.headers.get("x-ratelimit-requests-remaining"), "из",
          r.headers.get("x-ratelimit-requests-limit"))
    if data.get("errors"):
        print("ОШИБКА:", data["errors"]); sys.exit(1)
    out = ROOT / "data" / "leagues_raw.json"
    out.write_text(json.dumps(data, ensure_ascii=False))
    print(f"Сохранено {len(data['response'])} лиг -> {out}")
