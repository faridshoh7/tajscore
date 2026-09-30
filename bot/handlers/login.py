"""Вход на сайт: deep-link → Start → контакт → готово.

Пользователь ничего не набирает руками: имя и username берём из профиля
Telegram, телефон — из кнопки «Отправить номер».
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (KeyboardButton, Message, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove)

from app.config import ADMIN_TELEGRAM_ID, SITE_URL
from bot import repo

log = logging.getLogger("tajscore.bot.login")
router = Router(name="login")

CONTACT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
    resize_keyboard=True, one_time_keyboard=True,
    input_field_placeholder="Нажмите кнопку ниже",
)

ASK_CONTACT = (
    "Чтобы завершить вход, поделитесь номером телефона — нажмите кнопку "
    "«📱 Отправить номер» внизу.\n\n"
    "Имя мы возьмём из вашего профиля Telegram, вводить ничего не нужно. "
    "Номер нигде на сайте не показывается."
)


def display_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return name or (user.username or f"id{user.id}")


@router.message(CommandStart(deep_link=True))
async def start_with_token(message: Message, command: CommandObject, state: FSMContext):
    """Переход по ссылке с сайта: t.me/<bot>?start=<login_token>."""
    token = (command.args or "").strip()
    await state.update_data(login_token=token)
    name = display_name(message.from_user)
    await message.answer(
        f"Привет, {name}! 👋\n\nЭто вход на <b>Tajscore</b>.\n\n{ASK_CONTACT}",
        reply_markup=CONTACT_KB)


@router.message(CommandStart())
async def start_plain(message: Message, state: FSMContext):
    """Просто /start без токена — человек пришёл в бота сам."""
    await state.update_data(login_token=None)
    user = await repo.user_by_tg(message.from_user.id)
    if user:
        await repo.register(message.from_user.id, display_name(message.from_user),
                            message.from_user.username, None)
        await message.answer(
            f"С возвращением, {user['display_name']}!\n\n"
            f"Вы уже зарегистрированы. Чтобы войти на сайт, откройте {SITE_URL} "
            "и нажмите «Войти через Telegram» — я пришлю подтверждение сюда.",
            reply_markup=ReplyKeyboardRemove())
        return
    await message.answer(
        "Привет! Это бот <b>Tajscore</b> — футбольные результаты онлайн.\n\n"
        "Через меня работает вход на сайт: избранные команды и лиги, "
        "уведомления о матчах.\n\n" + ASK_CONTACT,
        reply_markup=CONTACT_KB)


@router.message(F.contact)
async def got_contact(message: Message, state: FSMContext, bot: Bot):
    contact = message.contact
    # Контакт можно переслать чужой — принимаем только собственный
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Это чужой контакт. Нажмите кнопку «📱 Отправить номер» — "
            "она отправляет именно ваш номер.", reply_markup=CONTACT_KB)
        return

    data = await state.get_data()
    token = data.get("login_token")
    await state.update_data(login_token=None)

    user, is_new = await repo.register(
        message.from_user.id, display_name(message.from_user),
        message.from_user.username, contact.phone_number)

    if is_new:
        await notify_admin_new_user(bot, user)

    if not token:
        await message.answer(
            f"Готово, {user['display_name']}! Вы зарегистрированы.\n\n"
            f"Теперь откройте {SITE_URL}, нажмите «Войти через Telegram» — "
            "и вы сразу окажетесь в своём аккаунте.",
            reply_markup=ReplyKeyboardRemove())
        return

    result = await repo.confirm_token(token, message.from_user.id)
    if result == "ok":
        await message.answer(
            "✅ <b>Готово! Вернись на сайт.</b>\n\n"
            "Вкладка Tajscore войдёт в аккаунт сама — ничего вводить не нужно.",
            reply_markup=ReplyKeyboardRemove())
    elif result == "expired":
        await message.answer(
            "⌛️ Ссылка для входа устарела — она живёт 5 минут.\n\n"
            "Вернитесь на сайт и нажмите «Войти через Telegram» ещё раз: "
            "номер уже сохранён, второй раз его не спросят.",
            reply_markup=ReplyKeyboardRemove())
    elif result == "used":
        await message.answer(
            "Эта ссылка уже сработала. Если сайт всё ещё просит войти — "
            "нажмите «Войти через Telegram» заново.",
            reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(
            "Не узнал ссылку для входа. Откройте сайт и нажмите "
            "«Войти через Telegram» ещё раз.", reply_markup=ReplyKeyboardRemove())


async def notify_admin_new_user(bot: Bot, user: dict) -> None:
    """Короткое уведомление админу о регистрации. Молча глотаем ошибку:
    из-за неё регистрация пользователя падать не должна."""
    if not ADMIN_TELEGRAM_ID:
        return
    uname = f" (@{user['username']})" if user["username"] else ""
    try:
        await bot.send_message(
            ADMIN_TELEGRAM_ID,
            f"🆕 Новый пользователь: {user['display_name']}{uname}")
    except Exception:
        log.warning("не удалось уведомить админа о новом пользователе", exc_info=True)


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Бот нужен для входа на <b>Tajscore</b>.\n\n"
        f"1. Откройте {SITE_URL}\n"
        "2. Нажмите «Войти через Telegram»\n"
        "3. Здесь нажмите Start и поделитесь номером\n\n"
        "Уведомления о матчах включаются и выключаются в профиле на сайте.")
