"""Вход на сайт и управление уведомлениями.

Вход возможен ТОЛЬКО по ссылке, которую выдал сайт: t.me/<bot>?start=<token>.
Просто /start в боте ничего не регистрирует и не впускает — только
подсказывает открыть сайт.

Как проходит вход:
  1. Сайт выдаёт одноразовую ссылку (живёт 5 минут) и ждёт.
  2. Новый человек один раз делится номером — больше его не спросят никогда.
  3. Бот показывает, КТО входит: устройство и время запроса — и спрашивает
     «Это вы?». Если ссылку прислал мошенник, человек видит чужое устройство,
     жмёт «Это не я», и вкладка мошенника получает отказ.
  4. «✅ Это я» — вкладка на сайте входит сама.

Все имена из профиля Telegram экранируются: бот отвечает в HTML-разметке, и
символ «<» в имени иначе ломал бы сообщение, а с ним и вход.
"""
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove)

from app.config import ADMIN_TELEGRAM_ID, SITE_URL
from bot import repo

log = logging.getLogger("tajscore.bot.login")
router = Router(name="login")
# Бот работает только в личке: в группах кнопки входа видели бы все
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

TZ = timezone(timedelta(hours=5))
TOKEN_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

CONTACT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
    resize_keyboard=True, one_time_keyboard=True,
    input_field_placeholder="Нажмите кнопку ниже",
)


def esc(s) -> str:
    return html.escape(str(s or ""))


def display_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return (name or user.username or f"id{user.id}")[:64]


def site_kb(extra: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🌐 Открыть Tajscore", url=SITE_URL + "/")]]
    return InlineKeyboardMarkup(inline_keyboard=(extra or []) + rows)


def menu_kb(user: dict) -> InlineKeyboardMarkup:
    on = bool(user.get("notifications_enabled"))
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [b(text="🔕 Выключить уведомления" if on else "🔔 Включить уведомления",
           callback_data="notif:off" if on else "notif:on")],
        [b(text="⚙️ Настроить уведомления", url=SITE_URL + "/?notify=1")],
        [b(text="🌐 Открыть Tajscore", url=SITE_URL + "/")],
    ])


def _valid_token(token: str) -> bool:
    return 16 <= len(token) <= 64 and set(token) <= TOKEN_CHARS


TOKEN_PROBLEMS = {
    "expired": "⌛️ Ссылка для входа устарела — она живёт 5 минут.\n\n"
               "Вернитесь на сайт и нажмите «Войти через Telegram» ещё раз.",
    "used": "Эта ссылка уже сработала. Если сайт всё ещё просит войти — "
            "нажмите «Войти через Telegram» заново.",
    "rejected": "Этот вход был отклонён. Если входите вы — начните заново на сайте.",
    "unknown": "Не узнал ссылку для входа. Откройте сайт и нажмите «Войти через Telegram».",
}


async def ask_confirm(message: Message, token: str) -> None:
    """Карточка «Это вы входите?» с устройством и временем запроса."""
    info = await repo.token_info(token)
    device = esc((info or {}).get("device") or "неизвестное устройство")
    when = datetime.fromtimestamp((info or {}).get("created_at") or 0, TZ).strftime("%H:%M")
    b = InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [b(text="✅ Это я, войти", callback_data=f"login:ok:{token}")],
        [b(text="❌ Это не я", callback_data=f"login:no:{token}")],
    ])
    await message.answer(
        "🔐 <b>Вход на Tajscore</b>\n\n"
        f"Устройство: <b>{device}</b>\n"
        f"Запрос создан в {when} (Душанбе)\n\n"
        "Это вы входите на сайт? Если ссылку вам прислал кто-то другой — "
        "нажмите «Это не я»: никто не получит доступ к вашему аккаунту.",
        reply_markup=kb)


# ------------------------------------------------------------------ /start
@router.message(CommandStart(deep_link=True))
async def start_with_token(message: Message, command: CommandObject, state: FSMContext):
    """Переход по ссылке с сайта: t.me/<bot>?start=<login_token>."""
    token = (command.args or "").strip()
    if not _valid_token(token):
        await message.answer(TOKEN_PROBLEMS["unknown"], reply_markup=site_kb())
        return
    status = await repo.token_status(token)
    if status != "ok":
        await message.answer(TOKEN_PROBLEMS.get(status, TOKEN_PROBLEMS["unknown"]),
                             reply_markup=site_kb())
        return

    user = await repo.user_by_tg(message.from_user.id)
    if user and user.get("phone"):
        # Уже зарегистрирован: номер второй раз не спрашиваем, сразу подтверждение
        await repo.register(message.from_user.id, display_name(message.from_user),
                            message.from_user.username, None)
        await ask_confirm(message, token)
        return

    # Новый человек: один раз просим номер, токен помним до ответа
    await state.update_data(login_token=token)
    await message.answer(
        f"Привет, {esc(display_name(message.from_user))}! 👋\n\n"
        "Это вход на <b>Tajscore</b>. Один раз поделитесь номером — "
        "нажмите кнопку «📱 Отправить номер» внизу. Больше спрашивать не будем.\n\n"
        "Имя возьмём из профиля Telegram. Номер нигде на сайте не показывается.",
        reply_markup=CONTACT_KB)


@router.message(CommandStart())
async def start_plain(message: Message, state: FSMContext):
    """Просто /start без токена. Регистрации здесь нет — только с сайта."""
    await state.update_data(login_token=None)
    user = await repo.user_by_tg(message.from_user.id)
    if user:
        if user.get("is_blocked"):
            await repo.mark_blocked(message.from_user.id, False)
            user["is_blocked"] = 0
        await message.answer(
            f"С возвращением, {esc(user['display_name'])}! ⚽\n\n"
            "Сюда приходят уведомления о голах и результатах ваших команд. "
            "Чтобы войти на сайте, нажмите там «Войти через Telegram» — "
            "я пришлю подтверждение.",
            reply_markup=ReplyKeyboardRemove())
        await message.answer(_status_text(user), reply_markup=menu_kb(user))
        return
    await message.answer(
        "Привет! Это бот <b>Tajscore</b> — футбол онлайн: Лигаи Олӣ, сборная, топ-лиги.\n\n"
        "Через меня работают вход на сайт и уведомления о голах.\n\n"
        "👉 Откройте сайт и нажмите «<b>Войти через Telegram</b>» — "
        "регистрация занимает пару секунд.",
        reply_markup=site_kb())


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
    if not token:
        await message.answer(
            "Номер получен, но вход начинается с сайта: откройте его и нажмите "
            "«Войти через Telegram».", reply_markup=ReplyKeyboardRemove())
        await message.answer("👇", reply_markup=site_kb())
        return

    user, is_new = await repo.register(
        message.from_user.id, display_name(message.from_user),
        message.from_user.username, contact.phone_number)
    if is_new:
        await notify_admin_new_user(bot, user)

    await message.answer("Спасибо! Номер сохранён ✅", reply_markup=ReplyKeyboardRemove())
    status = await repo.token_status(token)
    if status != "ok":
        await message.answer(TOKEN_PROBLEMS.get(status, TOKEN_PROBLEMS["unknown"]),
                             reply_markup=site_kb())
        return
    await ask_confirm(message, token)


# ------------------------------------------------------------------ подтверждение
@router.callback_query(F.data.startswith("login:"))
async def login_answer(cb: CallbackQuery):
    _, verdict, token = (cb.data.split(":", 2) + ["", ""])[:3]
    user = await repo.user_by_tg(cb.from_user.id)
    if not user or not _valid_token(token):
        await cb.answer("Начните вход заново на сайте", show_alert=True)
        return

    if verdict == "no":
        await repo.reject_token(token, cb.from_user.id)
        await cb.message.edit_text(
            "🛑 <b>Вход отменён.</b>\n\nВаш аккаунт в безопасности. Если вы сами "
            "не начинали вход — никому не пересылайте ссылки от Tajscore.")
        await cb.answer("Вход отклонён")
        if ADMIN_TELEGRAM_ID:
            log.warning("пользователь %s отклонил попытку входа", cb.from_user.id)
        return

    result = await repo.confirm_token(token, cb.from_user.id)
    if result == "ok":
        await cb.message.edit_text(
            "✅ <b>Готово! Вернитесь на сайт.</b>\n\n"
            "Вкладка Tajscore войдёт в аккаунт сама — ничего вводить не нужно.",
            reply_markup=site_kb())
        await cb.answer("Вход подтверждён")
        await cb.message.answer(_status_text(user), reply_markup=menu_kb(user))
    else:
        await cb.message.edit_text(TOKEN_PROBLEMS.get(result, TOKEN_PROBLEMS["unknown"]),
                                   reply_markup=site_kb())
        await cb.answer()


# ------------------------------------------------------------------ уведомления
def _status_text(user: dict) -> str:
    on = bool(user.get("notifications_enabled"))
    return ("🔔 <b>Уведомления включены.</b>\nПришлю голы, начало и итог матчей "
            "ваших команд и лиг. Подписаться — звёздочка ⭐ на сайте." if on else
            "🔕 <b>Уведомления выключены.</b>\nВключить можно кнопкой ниже.")


@router.message(Command("notify"))
async def notify_cmd(message: Message):
    user = await repo.user_by_tg(message.from_user.id)
    if not user:
        await message.answer("Сначала войдите на сайте через Telegram.", reply_markup=site_kb())
        return
    favs = await repo.fav_counts(user["id"])
    await message.answer(
        _status_text(user) +
        f"\n\nВ избранном: команд — {favs['team']}, лиг — {favs['league']}, матчей — {favs['match']}.",
        reply_markup=menu_kb(user))


@router.message(Command("stop"))
async def stop_cmd(message: Message):
    user = await repo.user_by_tg(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы — уведомлений и так нет.")
        return
    await repo.set_notifications(user["id"], False)
    user["notifications_enabled"] = 0
    await message.answer("🔕 Уведомления выключены. Включить — /notify.", reply_markup=menu_kb(user))


@router.callback_query(F.data.in_({"notif:on", "notif:off"}))
async def notif_toggle(cb: CallbackQuery):
    user = await repo.user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer("Сначала войдите на сайте", show_alert=True)
        return
    on = cb.data == "notif:on"
    await repo.set_notifications(user["id"], on)
    user["notifications_enabled"] = 1 if on else 0
    await cb.message.edit_text(_status_text(user), reply_markup=menu_kb(user))
    await cb.answer("Включены" if on else "Выключены")


@router.callback_query(F.data.regexp(r"^(mute|unmute):\d{1,12}$"))
async def mute_match(cb: CallbackQuery):
    """Кнопка под уведомлением: «Не уведомлять об этом матче» и обратно."""
    user = await repo.user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    action, fid = cb.data.split(":")
    muted = action == "mute"
    await repo.set_mute(user["id"], int(fid), muted)
    b = InlineKeyboardButton
    rows = [row for row in (cb.message.reply_markup.inline_keyboard if cb.message.reply_markup else [])
            if not any((btn.callback_data or "").startswith(("mute:", "unmute:")) for btn in row)]
    rows.append([b(text="🔔 Вернуть уведомления по матчу" if muted else "🔕 Не уведомлять об этом матче",
                   callback_data=f"{'unmute' if muted else 'mute'}:{fid}")])
    try:
        await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
    await cb.answer("Больше не пришлю по этому матчу" if muted else "Уведомления по матчу включены")


async def notify_admin_new_user(bot: Bot, user: dict) -> None:
    """Короткое уведомление админу о регистрации. Молча глотаем ошибку:
    из-за неё регистрация пользователя падать не должна."""
    if not ADMIN_TELEGRAM_ID:
        return
    uname = f" (@{esc(user['username'])})" if user["username"] else ""
    try:
        await bot.send_message(
            ADMIN_TELEGRAM_ID,
            f"🆕 Новый пользователь: {esc(user['display_name'])}{uname}")
    except Exception:
        log.warning("не удалось уведомить админа о новом пользователе", exc_info=True)


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Tajscore</b> — футбол онлайн.\n\n"
        "<b>Вход на сайт</b>\n"
        f"1. Откройте {SITE_URL}\n"
        "2. Нажмите «Войти через Telegram»\n"
        "3. Здесь подтвердите вход кнопкой «✅ Это я»\n\n"
        "<b>Уведомления</b>\n"
        "Нажмите ⭐ у команды, лиги или матча на сайте — я пришлю голы и результаты.\n"
        "/notify — включить или выключить\n"
        "/stop — выключить все уведомления\n\n"
        "Подробная настройка (какие события, тихие часы) — на сайте в настройках.",
        reply_markup=site_kb())


@router.message(F.text)
async def fallback(message: Message):
    """Любой другой текст — коротко объясняем, что умеет бот."""
    await message.answer("Я помогаю войти на сайт и присылаю уведомления о матчах. "
                         "Команды: /notify, /stop, /help", reply_markup=site_kb())
