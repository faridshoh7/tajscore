"""Конфигурация Tajscore: пути, лиги, интервалы синхронизации, лимит API."""
import os
import pathlib
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "tajscore.db"
SCHEMA_PATH = ROOT / "app" / "schema.sql"
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"

# ---------------------------------------------------------------- API-Football
API_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_BASE = "https://v3.football.api-sports.io"
API_HEADER = "x-apisports-key"
API_TIMEOUT = 30.0
MIN_REQUEST_GAP = 7.0   # сек между запросами: Free-тариф ограничен ~10 запросами в минуту

# Бесплатный тариф = 100 запросов/сутки. Держим запас, чтобы не упереться в стену.
DAILY_REQUEST_LIMIT = 100
DAILY_SOFT_LIMIT = 92          # воркер выше этого не поднимается
RESERVE_FOR_DETAILS = 12       # сколько из мягкого лимита бережём для карточек матчей

# Тариф. На "free" сезон 2026 закрыт для /standings, /players/*, /fixtures?league=season=,
# поэтому таблицы и статистику игроков считаем сами из собранных матчей и событий.
# Возьмёшь платный тариф — поставь "paid", и данные пойдут напрямую из API.
PLAN_TIER = "free"
USE_API_STANDINGS = PLAN_TIER != "free"
USE_API_PLAYER_STATS = PLAN_TIER != "free"

# Добор прошедших дат: с какой даты начинать заполнять историю сезона
BACKFILL_START = "2026-08-01"     # старт европейских сезонов
BACKFILL_START_TJK = "2026-04-01"  # Лигаи Олӣ идёт по календарному году
BACKFILL_PER_DAY = 25              # сколько запросов в сутки максимум тратим на историю
# Free-тариф отдаёт только вчера/сегодня/завтра, добирать историю нечем
BACKFILL_ENABLED = PLAN_TIER != "free"
DETAILS_PER_DAY = 12               # потолок на добор карточек матчей (из них считаются бомбардиры)

# ---------------------------------------------------------------- Часовой пояс
DEFAULT_TZ = "Asia/Dushanbe"   # UTC+5
DEFAULT_LANG = "ru"

# ---------------------------------------------------------------- Лиги
# id подтверждены запросом к /leagues (см. scripts/fetch_leagues.py).
# priority — порядок в левой колонке. group_stage=True — есть групповой этап и плей-офф.
LEAGUES = [
    {"id": 571, "priority": 1,  "season": 2026, "code": "TJK",
     "name_ru": "Лигаи Олӣ", "name_tg": "Лигаи Олӣ", "name_en": "Vysshaya Liga",
     "country_ru": "Таджикистан", "country_tg": "Тоҷикистон", "is_cup": False, "group_stage": False},

    {"id": 2,   "priority": 2,  "season": 2026, "code": "UCL",
     "name_ru": "Лига чемпионов УЕФА", "name_tg": "Лигаи қаҳрамонони УЕФА", "name_en": "UEFA Champions League",
     "country_ru": "Европа", "country_tg": "Аврупо", "is_cup": True, "group_stage": True},

    {"id": 39,  "priority": 3,  "season": 2026, "code": "ENG",
     "name_ru": "Премьер-лига", "name_tg": "Премер-лигаи Англия", "name_en": "Premier League",
     "country_ru": "Англия", "country_tg": "Англия", "is_cup": False, "group_stage": False},

    {"id": 140, "priority": 4,  "season": 2026, "code": "ESP",
     "name_ru": "Ла Лига", "name_tg": "Ла Лига", "name_en": "La Liga",
     "country_ru": "Испания", "country_tg": "Испания", "is_cup": False, "group_stage": False},

    {"id": 135, "priority": 5,  "season": 2026, "code": "ITA",
     "name_ru": "Серия А", "name_tg": "Серия А", "name_en": "Serie A",
     "country_ru": "Италия", "country_tg": "Италия", "is_cup": False, "group_stage": False},

    {"id": 78,  "priority": 6,  "season": 2026, "code": "GER",
     "name_ru": "Бундеслига", "name_tg": "Бундеслига", "name_en": "Bundesliga",
     "country_ru": "Германия", "country_tg": "Олмон", "is_cup": False, "group_stage": False},

    {"id": 61,  "priority": 7,  "season": 2026, "code": "FRA",
     "name_ru": "Лига 1", "name_tg": "Лигаи 1", "name_en": "Ligue 1",
     "country_ru": "Франция", "country_tg": "Фаронса", "is_cup": False, "group_stage": False},

    {"id": 3,   "priority": 8,  "season": 2026, "code": "UEL",
     "name_ru": "Лига Европы", "name_tg": "Лигаи Аврупо", "name_en": "UEFA Europa League",
     "country_ru": "Европа", "country_tg": "Аврупо", "is_cup": True, "group_stage": True},

    {"id": 848, "priority": 9,  "season": 2026, "code": "UECL",
     "name_ru": "Лига конференций", "name_tg": "Лигаи конфронсҳо", "name_en": "UEFA Conference League",
     "country_ru": "Европа", "country_tg": "Аврупо", "is_cup": True, "group_stage": True},

    {"id": 235, "priority": 10, "season": 2026, "code": "RUS",
     "name_ru": "РПЛ", "name_tg": "Премер-лигаи Русия", "name_en": "Russian Premier League",
     "country_ru": "Россия", "country_tg": "Русия", "is_cup": False, "group_stage": False},

    {"id": 307, "priority": 11, "season": 2026, "code": "KSA",
     "name_ru": "Про-лига Саудовской Аравии", "name_tg": "Про-лигаи Арабистони Саудӣ", "name_en": "Saudi Pro League",
     "country_ru": "Саудовская Аравия", "country_tg": "Арабистони Саудӣ", "is_cup": False, "group_stage": False},

    {"id": 253, "priority": 12, "season": 2026, "code": "USA",
     "name_ru": "MLS", "name_tg": "MLS", "name_en": "Major League Soccer",
     "country_ru": "США", "country_tg": "ИМА", "is_cup": False, "group_stage": False},

    {"id": 1,   "priority": 13, "season": 2026, "code": "WC",
     "name_ru": "Чемпионат мира", "name_tg": "Ҷоми ҷаҳон", "name_en": "World Cup",
     "country_ru": "Мир", "country_tg": "Ҷаҳон", "is_cup": True, "group_stage": True},

    {"id": 5,   "priority": 14, "season": 2026, "code": "UNL",
     "name_ru": "Лига наций УЕФА", "name_tg": "Лигаи миллатҳои УЕФА", "name_en": "UEFA Nations League",
     "country_ru": "Европа", "country_tg": "Аврупо", "is_cup": True, "group_stage": True},

    {"id": 4,   "priority": 15, "season": 2024, "code": "EURO",
     "name_ru": "Евро", "name_tg": "Евро", "name_en": "Euro Championship",
     "country_ru": "Европа", "country_tg": "Аврупо", "is_cup": True, "group_stage": True},
]

LEAGUE_IDS = [l["id"] for l in LEAGUES]
LEAGUE_BY_ID = {l["id"]: l for l in LEAGUES}
SEASON_BY_LEAGUE = {l["id"]: l["season"] for l in LEAGUES}

# Лиги для правой колонки «популярное» (если нет живых матчей)
POPULAR_LEAGUE_IDS = [571, 2, 39, 140, 135, 78]

# ---------------------------------------------------------------- Расписание синхронизации
# Все значения в секундах. Меняются в одном месте при апгрейде тарифа.
SYNC = {
    # Live-режим намеренно редкий: на free-тарифе опрос раз в 5 минут съедал
    # ~160 запросов в сутки при лимите 100. Раз в час — ~13, остальное
    # уходит на расписание и карточки матчей.
    "live_interval": 3600,         # опрос live-матчей (только когда матчи реально идут)
    "live_idle_interval": 7200,    # холостая проверка, когда живых матчей по расписанию нет
    "live_window_before": 900,     # за 15 мин до старта матча включаем live-режим
    "live_window_after": 5400,     # держим live-режим 90 мин после старта последнего матча
    "fixtures_today_interval": 21600,    # расписание на сегодня — раз в 6 часов
    "fixtures_around_interval": 43200,   # вчера/завтра — раз в 12 часов
    "fixtures_horizon_interval": 86400,  # +2..+7 дней — раз в сутки
    "standings_interval": 345600,        # таблица одной лиги — не чаще раза в 4 суток
    "players_interval": 604800,          # бомбардиры — раз в неделю на лигу
    "detail_live_ttl": 300,              # карточка идущего матча
    "detail_recent_ttl": 3600,           # карточка недавно завершённого
    "detail_final_ttl": 0,               # 0 = финальный матч больше не перезапрашиваем
    "h2h_ttl": 2592000,                  # личные встречи — месяц
    "tick": 30,                          # шаг главного цикла воркера
}

# Зоны турнирной таблицы: диапазоны мест -> класс подсветки
# (ЛЧ, ЛЕ, Лига конференций, вылет, стыки)
TABLE_ZONES = {
    39:  {"ucl": (1, 4), "uel": (5, 5), "uecl": (6, 6), "releg": (18, 20)},
    140: {"ucl": (1, 4), "uel": (5, 6), "uecl": (7, 7), "releg": (18, 20)},
    135: {"ucl": (1, 4), "uel": (5, 6), "uecl": (7, 7), "releg": (18, 20)},
    78:  {"ucl": (1, 4), "uel": (5, 6), "uecl": (7, 7), "playoff": (16, 16), "releg": (17, 18)},
    61:  {"ucl": (1, 4), "uel": (5, 5), "uecl": (6, 6), "playoff": (16, 16), "releg": (17, 18)},
    235: {"ucl": (1, 2), "uel": (3, 4), "uecl": (5, 5), "playoff": (13, 14), "releg": (15, 16)},
    # Таджикистан играет в зоне АФК, поэтому ключи зон свои — подписи
    # «Лига чемпионов»/«Лига Европы» здесь были бы просто неверны.
    571: {"acl": (1, 1), "acl2": (2, 2), "releg": (8, 8)},
    307: {"ucl": (1, 3), "uel": (4, 4), "releg": (15, 18)},
    253: {"ucl": (1, 7), "releg": (0, 0)},
}

# Сколько дней расписания держим в базе вперёд/назад
# На free-тарифе доступно только окно вчера..завтра, глубже ходить нельзя
FIXTURE_DAYS_AHEAD = 1 if PLAN_TIER == "free" else 7
FIXTURE_DAYS_BEHIND = 1 if PLAN_TIER == "free" else 3

# ---------------------------------------------------------------- Telegram-вход
# Значения только из .env: токен бота — такой же секрет, как ключ API.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Username без @ — из него собирается deep-link t.me/<username>?start=<token>
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID") or 0)

LOGIN_TOKEN_TTL = 300          # 5 минут на то, чтобы дойти до бота и нажать Start
SESSION_TTL = 180 * 86400      # сессия живёт полгода, продлевается при каждом заходе
SESSION_COOKIE = "ts_session"

# Рассылка: Telegram душит примерно на 30 сообщениях в секунду.
# Держимся заметно ниже — пачками с паузой.
BROADCAST_BATCH = 20
BROADCAST_PAUSE = 1.0          # сек между пачками

# Адрес сайта — бот подставляет его в кнопку «Вернуться на сайт»
SITE_URL = os.getenv("SITE_URL", "https://tajscore.duckdns.org").rstrip("/")
