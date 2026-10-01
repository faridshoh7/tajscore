"""Админ-панель бота: /admin.

Доступ строго по ADMIN_TELEGRAM_ID. Фильтр висит на самом роутере, поэтому
ни один хендлер отсюда не может случайно оказаться публичным: чужие апдейты
до них просто не доходят и остаются без ответа.
"""
import asyncio
import logging
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message, TelegramObject)

from app.config import ADMIN_TELEGRAM_ID, BROADCAST_BATCH, BROADCAST_PAUSE
from bot import repo

log = logging.getLogger("tajscore.bot.admin")


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(ADMIN_TELEGRAM_ID) and user is not None and user.id == ADMIN_TELEGRAM_ID


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class Broadcast(StatesGroup):
    text = State()
    confirm = State()


class Search(StatesGroup):
    term = State()


def menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [b(text="📊 Статистика", callback_data="adm:stats")],
        [b(text="📢 Рассылка", callback_data="adm:broadcast")],
        [b(text="🗄 База данных (CSV)", callback_data="adm:db")],
        [b(text="🔍 Поиск пользователя", callback_data="adm:search")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Меню", callback_data="adm:menu")]])


MENU_TEXT = "🛠 <b>Админ-панель Tajscore</b>\n\nВыберите раздел:"


@router.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=menu_kb())


@router.message(Command("cancel"), ~StateFilter(None))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=menu_kb())


@router.callback_query(F.data == "adm:menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(MENU_TEXT, reply_markup=menu_kb())
    await cb.answer()


# ------------------------------------------------------------------ статистика
@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery):
    s = await repo.stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Всего пользователей: <b>{s['total']}</b>\n"
        f"Новых за сегодня: <b>{s['today']}</b>\n"
        f"Новых за неделю: <b>{s['week']}</b>\n"
        f"С уведомлениями: <b>{s['notify']}</b>\n"
        f"Активных за неделю: <b>{s['active']}</b>\n"
        f"Заблокировали бота: <b>{s['blocked']}</b>\n"
        f"Записей в избранном: <b>{s['favorites']}</b>"
    )
    await cb.message.edit_text(text, reply_markup=back_kb())
    await cb.answer()


# ------------------------------------------------------------------ база данных
@router.callback_query(F.data == "adm:db")
async def dump_db(cb: CallbackQuery):
    await cb.answer("Готовлю файл…")
    data = await repo.csv_bytes()
    name = f"tajscore-users-{time.strftime('%Y%m%d-%H%M')}.txt"
    s = await repo.stats()
    await cb.message.answer_document(
        BufferedInputFile(data, filename=name),
        caption=f"🗄 Выгрузка пользователей: {s['total']} записей.",
        reply_markup=back_kb())


# ------------------------------------------------------------------ поиск
@router.callback_query(F.data == "adm:search")
async def search_ask(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Search.term)
    await cb.message.edit_text(
        "🔍 Пришлите <b>telegram_id</b>, <b>@username</b> или часть имени.\n\n"
        "/cancel — отмена.", reply_markup=back_kb())
    await cb.answer()


@router.message(Search.term)
async def search_do(message: Message, state: FSMContext):
    term = (message.text or "").strip()
    if not term:
        await message.answer("Нужен текст: id, @username или часть имени. /cancel — отмена.")
        return
    found = await repo.find_users(term)
    await state.clear()
    if not found:
        await message.answer("Ничего не нашёл.", reply_markup=menu_kb())
        return
    blocks = []
    for u in found:
        uname = f"@{u['username']}" if u["username"] else "—"
        blocks.append(
            f"👤 <b>{u['display_name']}</b>\n"
            f"telegram_id: <code>{u['telegram_id']}</code>\n"
            f"username: {uname}\n"
            f"телефон: <code>{u['phone'] or '—'}</code>\n"
            f"регистрация: {repo.fmt_ts(u['created_at'])}\n"
            f"последний вход: {repo.fmt_ts(u['last_login'])}\n"
            f"уведомления: {'вкл' if u['notifications_enabled'] else 'выкл'}"
            + ("\n⛔️ заблокировал бота" if u["is_blocked"] else ""))
    head = "" if len(blocks) == 1 else f"Найдено: {len(blocks)}\n\n"
    await message.answer(head + "\n\n".join(blocks), reply_markup=menu_kb())


# ------------------------------------------------------------------ рассылка
@router.callback_query(F.data == "adm:broadcast")
async def bc_ask(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.text)
    await cb.message.edit_text(
        "📢 Пришлите <b>текст рассылки</b>.\n\n"
        "Форматирование (жирный, ссылки, эмодзи) сохраняется как в вашем сообщении.\n"
        "/cancel — отмена.", reply_markup=back_kb())
    await cb.answer()


@router.message(Broadcast.text, F.text.startswith("/"))
async def bc_command_instead_of_text(message: Message):
    """Команду легко отправить по привычке — не рассылать же её всем."""
    await message.answer("Это похоже на команду, а не на текст рассылки. "
                         "Пришлите текст или /cancel.")


@router.message(Broadcast.text, F.text)
async def bc_preview(message: Message, state: FSMContext):
    # html_text сохраняет разметку исходного сообщения (жирный, ссылки, эмодзи)
    body = message.html_text
    await state.update_data(body=body)
    await state.set_state(Broadcast.confirm)

    all_ids = await repo.recipients(False)
    notify_ids = await repo.recipients(True)
    b = InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [b(text=f"📨 Всем ({len(all_ids)})", callback_data="adm:send:all")],
        [b(text=f"🔔 С уведомлениями ({len(notify_ids)})", callback_data="adm:send:notify")],
        [b(text="✖️ Отмена", callback_data="adm:menu")],
    ])
    await message.answer(
        "<b>Предпросмотр — так увидят пользователи:</b>\n"
        "─────────────\n" + body + "\n─────────────\n\nКому отправляем?",
        reply_markup=kb)


@router.message(Broadcast.text)
async def bc_wrong_type(message: Message):
    await message.answer("Нужен текст. Пришлите сообщение текстом или /cancel.")


@router.callback_query(Broadcast.confirm, F.data.startswith("adm:send:"))
async def bc_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    only_notify = cb.data.endswith(":notify")
    data = await state.get_data()
    body = data.get("body")
    await state.clear()
    if not body:
        await cb.message.edit_text("Текст потерялся, начните заново.", reply_markup=menu_kb())
        await cb.answer()
        return

    await cb.answer("Запускаю рассылку")
    ids = await repo.recipients(only_notify)
    audience = "с уведомлениями" if only_notify else "всем"
    if not ids:
        await cb.message.edit_text("Некому отправлять: получателей нет.", reply_markup=menu_kb())
        return

    progress = await cb.message.edit_text(
        f"📤 Рассылка ({audience}): 0 / {len(ids)}…")
    result = await _broadcast(bot, ids, body, progress)
    await progress.edit_text(
        f"✅ <b>Рассылка завершена</b> ({audience})\n\n"
        f"Получателей: <b>{len(ids)}</b>\n"
        f"Доставлено: <b>{result['sent']}</b>\n"
        f"Заблокировали бота: <b>{result['blocked']}</b>\n"
        f"Прочие ошибки: <b>{result['failed']}</b>\n"
        f"Заняло: {result['elapsed']} с",
        reply_markup=menu_kb())


async def _broadcast(bot: Bot, ids: list[int], body: str, progress: Message) -> dict:
    """Шлём пачками по BROADCAST_BATCH с паузой.

    Telegram режет примерно на 30 сообщениях в секунду и на превышение отвечает
    429 с полем retry_after — его отрабатываем честной паузой, а не потерей письма.
    """
    sent = blocked = failed = 0
    started = time.monotonic()

    async def one(chat_id: int) -> str:
        for attempt in range(2):
            try:
                await bot.send_message(chat_id, body, disable_web_page_preview=True)
                return "sent"
            except TelegramRetryAfter as e:
                if attempt:
                    return "failed"
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                # пользователь заблокировал бота — больше его не тревожим
                await repo.mark_blocked(chat_id)
                return "blocked"
            except TelegramBadRequest:
                return "failed"
            except Exception:
                log.warning("рассылка: сбой на %s", chat_id, exc_info=True)
                return "failed"
        return "failed"

    for i in range(0, len(ids), BROADCAST_BATCH):
        batch = ids[i:i + BROADCAST_BATCH]
        for outcome in await asyncio.gather(*(one(cid) for cid in batch)):
            if outcome == "sent":
                sent += 1
            elif outcome == "blocked":
                blocked += 1
            else:
                failed += 1
        done = i + len(batch)
        if done < len(ids):
            try:
                await progress.edit_text(
                    f"📤 Рассылка: {done} / {len(ids)}…\n"
                    f"доставлено {sent}, ошибок {blocked + failed}")
            except TelegramBadRequest:
                pass   # «message is not modified» — не повод падать
            await asyncio.sleep(BROADCAST_PAUSE)

    return {"sent": sent, "blocked": blocked, "failed": failed,
            "elapsed": round(time.monotonic() - started, 1)}
