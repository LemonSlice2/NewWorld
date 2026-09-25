"""Клавиатуры.

В ``callback_data`` Telegram отводит 64 байта, поэтому туда кладётся не
описание действия, а его короткий адрес: номер хода и позиция варианта.
Номер хода нужен, чтобы кнопка из прокрученного вверх сообщения не сработала.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.content import Option

ACTION_PREFIX = "a"
MAX_LABEL = 60


def action_keyboard(turn_number: int, options: tuple[Option, ...]) -> InlineKeyboardMarkup | None:
    if not options:
        return None
    rows = [
        [
            InlineKeyboardButton(
                text=_clip(option.label),
                callback_data=f"{ACTION_PREFIX}:{turn_number}:{index}",
            )
        ]
        for index, option in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_action(data: str) -> tuple[int, int] | None:
    """Разобрать callback_data. None — чужие или испорченные данные."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != ACTION_PREFIX:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _clip(label: str) -> str:
    """Подпись кнопки не должна расползаться на несколько строк."""
    if len(label) <= MAX_LABEL:
        return label
    return label[: MAX_LABEL - 1].rstrip() + "…"
