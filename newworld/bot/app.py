"""Обработчики Telegram.

Одно сообщение на сцену: при каждом ходе оно перерисовывается, а не
дублируется новым. Так игрок не листает простыню, а бот не упирается в
ограничение Telegram на частоту сообщений в один чат.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..core.engine import InvalidAction, Turn
from ..views import render_status
from .keyboards import action_keyboard, parse_action
from .service import GameService, StaleAction

logger = logging.getLogger(__name__)

# Предел Telegram — 4096 символов; оставляем запас под статус и разметку.
MAX_MESSAGE = 3800

HELP = (
    "<b>Как играть</b>\n\n"
    "Нажимай на кнопки под сообщением — это твои действия.\n"
    "Броски костей показываются открыто: видно, что выпало и против чего.\n\n"
    "/new — начать заново\n"
    "/status — карточка персонажа\n"
    "/help — эта справка"
)


def build_router(game: GameService) -> Router:
    router = Router()

    # --- отрисовка ----------------------------------------------------

    def render(turn: Turn) -> str:
        text = game.narrator.narrate(turn)
        if len(text) > MAX_MESSAGE:
            text = text[:MAX_MESSAGE].rsplit("\n", 1)[0] + "\n…"
        status = render_status(turn.state.character)
        footer = "" if turn.options else "\n\n<i>Забег окончен. /new — начать заново.</i>"
        return f"{text}\n\n➖➖➖\n{status}{footer}"

    async def send_turn(message: Message, turn: Turn) -> None:
        await message.answer(
            render(turn),
            reply_markup=action_keyboard(turn.state.turn, turn.options),
        )

    async def edit_turn(callback: CallbackQuery, turn: Turn) -> None:
        """Перерисовать сообщение сцены; если не вышло — прислать новое."""
        try:
            await callback.message.edit_text(
                render(turn),
                reply_markup=action_keyboard(turn.state.turn, turn.options),
            )
        except TelegramBadRequest as exc:
            # Сообщение слишком старое, удалено, или текст не изменился.
            if "message is not modified" in str(exc):
                return
            logger.info("Не удалось отредактировать сообщение, шлю новое: %s", exc)
            await callback.message.answer(
                render(turn),
                reply_markup=action_keyboard(turn.state.turn, turn.options),
            )

    # --- команды ------------------------------------------------------

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        existing = await game.resume(user.id)
        if existing is not None and existing.options:
            await message.answer("У тебя есть незаконченный забег. Продолжаем.")
            await send_turn(message, existing)
            return
        await message.answer(HELP)
        turn = await game.start_new(user.id, user.first_name or "Путник")
        await send_turn(message, turn)

    @router.message(Command("new"))
    async def on_new(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        turn = await game.start_new(user.id, user.first_name or "Путник")
        await message.answer("Новый забег.")
        await send_turn(message, turn)

    @router.message(Command("status"))
    async def on_status(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        turn = await game.resume(user.id)
        if turn is None:
            await message.answer("Забег ещё не начат. /new — начать.")
            return
        await message.answer(render_status(turn.state.character))

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await message.answer(HELP)

    # --- действия -----------------------------------------------------

    @router.callback_query(F.data.startswith("a:"))
    async def on_action(callback: CallbackQuery) -> None:
        user = callback.from_user
        parsed = parse_action(callback.data or "")
        if parsed is None or callback.message is None:
            await callback.answer("Не понял действие")
            return
        expected_turn, option_index = parsed
        try:
            turn = await game.act(user.id, expected_turn, option_index)
        except StaleAction as exc:
            # Частый случай: игрок пролистал вверх и жмёт старую кнопку.
            await callback.answer(str(exc), show_alert=True)
            return
        except InvalidAction as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.answer()
        await edit_turn(callback, turn)

    return router
