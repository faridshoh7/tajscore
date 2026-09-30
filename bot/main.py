"""Точка входа Telegram-бота. Запуск: python -m bot.main

Работает на long polling: бот сам ходит на api.telegram.org по HTTPS с токеном.
Входящего эндпоинта нет, подделать апдейт снаружи нельзя — отдельная проверка
подписи, как при webhook, здесь не нужна. Перейдёте на webhook — понадобится
secret_token и роут в nginx.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app import auth, db
from app.config import ADMIN_TELEGRAM_ID, TELEGRAM_BOT_TOKEN
from bot.handlers import admin as admin_handlers
from bot.handlers import login as login_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tajscore.bot")


async def set_commands(bot: Bot) -> None:
    """Публичный список команд. /admin туда не кладём — незачем показывать
    его всем подряд; у админа он и так работает."""
    await bot.set_my_commands([
        BotCommand(command="start", description="Вход на Tajscore"),
        BotCommand(command="help", description="Как это работает"),
    ])


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env — бот не запускается")
    if not ADMIN_TELEGRAM_ID:
        log.warning("ADMIN_TELEGRAM_ID не задан: админ-панель будет недоступна никому")

    db.init_db()
    auth.cleanup()

    bot = Bot(TELEGRAM_BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    # admin первым: его роутер отфильтрован по ADMIN_TELEGRAM_ID, чужие апдейты
    # спокойно проходят дальше в публичные хендлеры
    dp.include_router(admin_handlers.router)
    dp.include_router(login_handlers.router)

    me = await bot.get_me()
    log.info("Бот @%s запущен", me.username)
    await set_commands(bot)

    try:
        # накопившиеся за простой апдейты не отыгрываем: старые login-токены
        # всё равно протухли, а рассылку дважды запускать нельзя
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен")
