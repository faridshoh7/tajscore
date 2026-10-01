"""Слой доступа к SQLite. Соединение — своё на поток (FastAPI + воркер)."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from app.config import DB_PATH, SCHEMA_PATH, LEAGUES

_local = threading.local()
_write_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _local.conn = _connect()
    return conn


@contextmanager
def write():
    """Транзакция на запись. Пишем по одному потоку за раз — SQLite так спокойнее."""
    conn = get_conn()
    with _write_lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params=()) -> list[sqlite3.Row]:
    conn = get_conn()
    conn.commit()
    return conn.execute(sql, params).fetchall()


def query_one(sql: str, params=()):
    conn = get_conn()
    conn.commit()
    return conn.execute(sql, params).fetchone()


def execute(sql: str, params=()):
    with write() as conn:
        return conn.execute(sql, params)


def executemany(sql: str, seq):
    with write() as conn:
        return conn.executemany(sql, seq)


# ------------------------------------------------------------------ инициализация
def _migrate(conn) -> None:
    """Добавляет колонки, появившиеся после первого запуска.

    CREATE TABLE IF NOT EXISTS не меняет уже созданную таблицу, поэтому
    новые поля досыпаем здесь. ALTER TABLE ADD COLUMN не идемпотентен —
    сверяемся с PRAGMA table_info.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(player_stats)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE player_stats ADD COLUMN source TEXT DEFAULT 'calc'")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fixtures)")}
    if "venue_capacity" not in cols:
        conn.execute("ALTER TABLE fixtures ADD COLUMN venue_capacity INTEGER")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(person_names)")}
    for col, decl in (("photo", "TEXT"), ("photo_author", "TEXT"),
                      ("photo_license", "TEXT"), ("photo_checked_at", "INTEGER DEFAULT 0")):
        if col not in cols:
            conn.execute(f"ALTER TABLE person_names ADD COLUMN {col} {decl}")
    # devices table
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "devices" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id    TEXT PRIMARY KEY,
                device_name  TEXT,
                ua           TEXT,
                first_seen   INTEGER NOT NULL,
                last_seen    INTEGER NOT NULL,
                visits       INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_devices_last ON devices(last_seen);
        """)


def init_db() -> None:
    """Создаёт таблицы и заливает справочник лиг из config.py."""
    conn = get_conn()
    with _write_lock:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)
        conn.commit()
    seed_leagues()


def seed_leagues() -> None:
    """Названия/приоритеты берём из конфига, logo и flag дописывает воркер из API."""
    rows = [
        (l["id"], l["name_en"], l["name_ru"], l["name_tg"], l["country_ru"],
         l["country_ru"], l["country_tg"], l["code"], l["season"],
         int(l["is_cup"]), int(l["group_stage"]), l["priority"])
        for l in LEAGUES
    ]
    with write() as conn:
        conn.executemany(
            """INSERT INTO leagues (id, name, name_ru, name_tg, country, country_ru,
                                    country_tg, code, season, is_cup, group_stage, priority)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, name_ru=excluded.name_ru, name_tg=excluded.name_tg,
                   country=excluded.country, country_ru=excluded.country_ru,
                   country_tg=excluded.country_tg, code=excluded.code,
                   season=excluded.season, is_cup=excluded.is_cup,
                   group_stage=excluded.group_stage, priority=excluded.priority""",
            rows,
        )
        # У виртуальной лиги «Сборная Таджикистана» нет API-источника, который
        # проставит лого, поэтому ставим его здесь — флаг Таджикистана.
        from app.config import NATIONAL_TEAM
        nt_id = NATIONAL_TEAM["league_id"]
        flag = "https://media.api-sports.io/flags/tj.svg"
        conn.execute("UPDATE leagues SET logo=?, flag=? WHERE id=? AND logo IS NULL",
                     (flag, flag, nt_id))


# ------------------------------------------------------------------ утилиты
def get_meta(key: str, default=None):
    row = query_one("SELECT value FROM meta WHERE key=?", (key,))
    return row["value"] if row else default


def set_meta(key: str, value) -> None:
    execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_sync_state(key: str) -> dict:
    row = query_one("SELECT * FROM sync_state WHERE key=?", (key,))
    return dict(row) if row else {"key": key, "last_run": 0, "last_ok": 0, "last_error": None, "note": None}


def mark_sync(key: str, ok: bool = True, error: str | None = None, note: str | None = None) -> None:
    now = int(time.time())
    execute(
        """INSERT INTO sync_state(key, last_run, last_ok, last_error, note)
           VALUES(?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET
               last_run=excluded.last_run,
               last_ok=CASE WHEN ? THEN excluded.last_run ELSE sync_state.last_ok END,
               last_error=excluded.last_error,
               note=COALESCE(excluded.note, sync_state.note)""",
        (key, now, now if ok else 0, error, note, 1 if ok else 0),
    )


def upsert(table: str, data: dict, pk: list[str], conn: sqlite3.Connection | None = None) -> None:
    """Универсальный INSERT ... ON CONFLICT DO UPDATE."""
    cols = list(data.keys())
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT({','.join(pk)}) DO UPDATE SET {updates}") if updates else (
           f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})")
    values = [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in data.values()]
    if conn is not None:
        conn.execute(sql, values)
    else:
        execute(sql, values)
