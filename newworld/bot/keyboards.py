"""Клавиатуры.

В ``callback_data`` Telegram отводит 64 байта, поэтому туда кладётся не
описание выбора, а его короткий адрес: позиции в списках и номер хода.
Номер хода нужен, чтобы кнопка из прокрученного вверх сообщения не
сработала во второй раз.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.content import CharacterClass, Option, Subclass
from ..core.models import Gender

ACTION_PREFIX = "a"
GENDER_PREFIX = "g"
CLASS_PREFIX = "c"
SUBCLASS_PREFIX = "s"
SKIP_NAME = "noname"
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


def class_keyboard(
    classes: tuple[CharacterClass, ...], gender: Gender
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_clip(character_class.name.for_gender(gender)),
                callback_data=f"{CLASS_PREFIX}:{index}",
            )
        ]
        for index, character_class in enumerate(classes)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=gender.label, callback_data=f"{GENDER_PREFIX}:{gender.value}"
                )
                for gender in Gender
            ]
        ]
    )


def subclass_keyboard(
    class_index: int, subclasses: tuple[Subclass, ...], gender: Gender
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_clip(subclass.name.for_gender(gender)),
                callback_data=f"{SUBCLASS_PREFIX}:{class_index}:{index}",
            )
        ]
        for index, subclass in enumerate(subclasses)
    ]
    rows.append(
        [InlineKeyboardButton(text="← Другой класс", callback_data=f"{CLASS_PREFIX}:back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_name_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оставить без имени", callback_data=SKIP_NAME)]
        ]
    )


def parse_action(data: str) -> tuple[int, int] | None:
    """Разобрать действие в сцене. None — чужие или испорченные данные."""
    return _parse_pair(data, ACTION_PREFIX)


def parse_class(data: str) -> int | None:
    """Разобрать выбор класса. None — не выбор класса."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != CLASS_PREFIX:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def parse_subclass(data: str) -> tuple[int, int] | None:
    """Разобрать выбор специализации."""
    return _parse_pair(data, SUBCLASS_PREFIX)


def _parse_pair(data: str, prefix: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != prefix:
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


def parse_gender(data: str) -> Gender | None:
    """Разобрать выбор пола. None — не выбор пола."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != GENDER_PREFIX:
        return None
    try:
        return Gender(parts[1])
    except ValueError:
        return None
