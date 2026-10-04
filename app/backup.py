"""Еженедельный бэкап базы: копия SQLite, сжатая gzip, уходит админу в Telegram.

Копия снимается штатным механизмом sqlite3.backup — он корректно работает на
живой базе в режиме WAL, в отличие от простого копирования файла. Последние
четыре архива остаются и на диске, в data/backups/.

В базе лежат телефоны пользователей, поэтому архив отправляется только на
ADMIN_TELEGRAM_ID и больше никуда.
"""
import asyncio
import gzip
import logging
import sqlite3
import time
from datetime import datetime

from app import db
from app.config import ADMIN_TELEGRAM_ID, DATA_DIR, DB_PATH

log = logging.getLogger("tajscore.backup")

BACKUP_DIR = DATA_DIR / "backups"
INTERVAL = 7 * 86400
KEEP = 4
TG_LIMIT = 49 * 1024 * 1024      # Bot API принимает документы до 50 МБ


def make() -> tuple[str, bytes]:
    """Снимает копию и возвращает (имя файла, сжатые байты)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    raw = BACKUP_DIR / f"tajscore-{stamp}.db"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(raw)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    data = gzip.compress(raw.read_bytes(), compresslevel=6)
    raw.unlink(missing_ok=True)
    name = f"tajscore-{stamp}.db.gz"
    path = BACKUP_DIR / name
    path.write_bytes(data)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    for old in sorted(BACKUP_DIR.glob("tajscore-*.db.gz"))[:-KEEP]:
        old.unlink(missing_ok=True)
    return name, data


async def run_if_due(force: bool = False) -> bool:
    last = db.get_sync_state("backup")["last_ok"]
    if not force and int(time.time()) - last < INTERVAL:
        return False
    try:
        name, data = await asyncio.to_thread(make)
    except Exception:
        log.exception("бэкап не удался")
        db.mark_sync("backup", ok=False, error="ошибка копирования")
        return False
    size_mb = len(data) / 1024 / 1024
    sent = False
    if ADMIN_TELEGRAM_ID and len(data) <= TG_LIMIT:
        from app.notify import telegram as tg
        users = db.query_one("SELECT COUNT(*) n FROM users")["n"]
        sent = await tg.send_document(
            ADMIN_TELEGRAM_ID, name, data,
            caption=f"🗄 <b>Еженедельный бэкап Tajscore</b>\n"
                    f"Размер: {size_mb:.1f} МБ · пользователей: {users}\n"
                    f"Хранить в надёжном месте: внутри телефоны пользователей.")
    db.mark_sync("backup", ok=True,
                 note=f"{name}, {size_mb:.1f} МБ, " + ("отправлен в Telegram" if sent else "только на диске"))
    log.info("Бэкап готов: %s (%.1f МБ), в Telegram: %s", name, size_mb, sent)
    return True
