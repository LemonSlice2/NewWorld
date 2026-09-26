"""Обработчики Telegram.

Одно сообщение на сцену: при каждом ходе оно перерисовывается, а не
дублируется новым. Так игрок не листает простыню, а бот не упирается в
ограничение Telegram на частоту сообщений в один чат.

Создание персонажа идёт тремя шагами — класс, специализация, имя, — и
только на шаге имени боту нужно дождаться обычного сообщения. Для этого
состояние держится в FSM: оно живёт секунды и не заслуживает записи в
базу.
"""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..core.engine import InvalidAction, Turn
from ..core.gendered import inflect
from ..views import render_status
from ..core.models import Gender
from .keyboards import (
    SKIP_NAME,
    action_keyboard,
    class_keyboard,
    gender_keyboard,
    parse_action,
    parse_class,
    parse_gender,
    parse_subclass,
    skip_name_keyboard,
    subclass_keyboard,
)
from .health_bar import HealthBarImages
from .service import GameService, SaveOutdated, StaleAction

logger = logging.getLogger(__name__)

# Предел Telegram — 4096 символов; оставляем запас под статус и разметку.
MAX_MESSAGE = 3800
# Имя длиннее строки кнопки только мешает читать карточку персонажа.
MAX_NAME = 24

HELP = (
    "<b>Как играть</b>\n\n"
    "Нажимай на кнопки под сообщением — это твои действия.\n"
    "Броски костей показываются открыто: видно, что выпало и против чего.\n\n"
    "/new — создать нового персонажа\n"
    "/status — карточка персонажа\n"
    "/help — эта справка"
)


class Creation(StatesGroup):
    """Создание героя.

    Выбор пола, класса и специализации делается кнопками, а имя приходит
    обычным сообщением — ради него и нужно состояние. Заодно оно держит
    уже сделанные выборы: они живут секунды и не заслуживают записи в базу.
    """

    building = State()
    waiting_for_name = State()


def clean_name(raw: str) -> str:
    """Привести введённое имя к тому, что не сломает карточку персонажа."""
    name = " ".join(raw.split())
    return name[:MAX_NAME].strip()


def build_router(game: GameService, health_bar: HealthBarImages | None = None) -> Router:
    router = Router()
    health_bar = health_bar or HealthBarImages()

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
            if "message is not modified" in str(exc):
                return
            logger.info("Не удалось отредактировать сообщение, шлю новое: %s", exc)
            await callback.message.answer(
                render(turn),
                reply_markup=action_keyboard(turn.state.turn, turn.options),
            )


    async def send_status(message: Message, turn: Turn) -> None:
        """Карточка персонажа. С нарисованной полосой здоровья, если она есть.

        Подпись к фото Telegram ограничивает 1024 символами — карточка в
        него укладывается, в отличие от текста сцены. Поэтому картинка
        живёт здесь, а не под каждым ходом.
        """
        character = turn.state.character
        caption = render_status(character, with_bar=not health_bar.available)

        cached = health_bar.cached_id(character)
        if cached is not None:
            await message.answer_photo(cached, caption=caption)
            return

        path = health_bar.path_for(character)
        if path is None:
            await message.answer(caption)
            return
        photo = BufferedInputFile(path.read_bytes(), filename=path.name)
        try:
            sent = await message.answer_photo(photo, caption=caption)
        except TelegramBadRequest as exc:
            # Картинка испорчена или не подходит Telegram — карточка важнее.
            logger.warning("Не удалось отправить полосу здоровья (%s): %s", path.name, exc)
            await message.answer(caption)
            return
        if sent.photo:
            health_bar.remember(character, sent.photo[-1].file_id)

    # --- создание персонажа -------------------------------------------

    async def offer_gender(message: Message, with_world: bool = True) -> None:
        if with_world and game.story.world_intro:
            title = game.story.world_title or "Мир"
            await message.answer(f"<b>{title}</b>\n\n{game.story.world_intro}")
        await message.answer(
            "<b>Кто пойдёт в Ольховец?</b>", reply_markup=gender_keyboard()
        )

    async def offer_classes(message: Message, gender: Gender) -> None:
        lines = ["<b>Кем ты был{|а} до этой дороги?</b>", ""]
        for character_class in game.classes:
            lines.append(
                f"<b>{character_class.name.for_gender(gender)}</b> — {character_class.tagline}"
            )
        await message.answer(
            inflect("\n".join(lines), gender),
            reply_markup=class_keyboard(game.classes, gender),
        )

    async def offer_subclasses(message: Message, class_index: int, gender: Gender) -> None:
        character_class = game.classes[class_index]
        subclasses = game.subclasses_of(character_class)
        lines = [
            f"<b>{character_class.name.for_gender(gender)}</b>",
            "",
            character_class.description,
            "",
            "<b>Чем ты занимал{ся|ась} в этом ремесле?</b>",
            "",
        ]
        for subclass in subclasses:
            lines.append(f"<b>{subclass.name.for_gender(gender)}</b> — {subclass.tagline}")
        await message.answer(
            inflect("\n".join(lines), gender),
            reply_markup=subclass_keyboard(class_index, subclasses, gender),
        )

    async def ask_name(
        message: Message, class_index: int, subclass_index: int, gender: Gender
    ) -> None:
        character_class = game.classes[class_index]
        subclass = game.subclasses_of(character_class)[subclass_index]
        await message.answer(
            inflect(
                f"<b>{subclass.name.for_gender(gender)}</b>\n\n{subclass.description}\n\n"
                "<b>Как {его|её} зовут?</b>\nНапиши имя одним сообщением.",
                gender,
            ),
            reply_markup=skip_name_keyboard(),
        )

    async def create_and_start(
        message: Message,
        user_id: int,
        name: str,
        gender: Gender,
        class_index: int,
        subclass_index: int,
    ) -> None:
        character_class = game.classes[class_index]
        subclasses = game.subclasses_of(character_class)
        subclass = subclasses[subclass_index] if subclasses else None
        turn = await game.start_new(user_id, name, gender, character_class, subclass)
        character = turn.state.character
        await message.answer(
            f"<b>{html.escape(character.name)}</b>\n<i>{html.escape(character.origin)}</i>"
        )
        await send_turn(message, turn)

    # --- команды ------------------------------------------------------

    @router.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            existing = await game.resume(user.id)
        except SaveOutdated:
            await message.answer(
                "Сюжет с тех пор обновился, и прошлый забег продолжить нельзя. "
                "Создадим героя заново."
            )
            existing = None
        if existing is not None and existing.options:
            await message.answer("У тебя есть незаконченный забег. Продолжаем.")
            await send_turn(message, existing)
            return
        await message.answer(HELP)
        if game.classes:
            await state.set_state(Creation.building)
            await offer_gender(message)
            return
        turn = await game.start_new(user.id, user.first_name or "Путник")
        await send_turn(message, turn)

    @router.message(Command("new"))
    async def on_new(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        if game.classes:
            await state.set_state(Creation.building)
            await offer_gender(message, with_world=False)
            return
        turn = await game.start_new(user.id, user.first_name or "Путник")
        await send_turn(message, turn)

    @router.message(Command("status"))
    async def on_status(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        try:
            turn = await game.resume(user.id)
        except SaveOutdated:
            turn = None
        if turn is None:
            await message.answer("Забег ещё не начат. /new — создать героя.")
            return
        await send_status(message, turn)

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await message.answer(HELP)

    # --- шаги создания -------------------------------------------------

    @router.callback_query(F.data.startswith("g:"))
    async def on_gender(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.message is None:
            return
        gender = parse_gender(callback.data or "")
        await callback.answer()
        if gender is None:
            await callback.message.answer("Не понял выбор. /new — начать сначала.")
            return
        await _drop_buttons(callback)
        await state.set_state(Creation.building)
        await state.update_data(gender=gender.value)
        await offer_classes(callback.message, gender)

    @router.callback_query(F.data.startswith("c:"))
    async def on_class(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.message is None:
            return
        gender = await _gender_from(state)
        await callback.answer()
        await _drop_buttons(callback)
        if callback.data == "c:back":
            await offer_classes(callback.message, gender)
            return
        index = parse_class(callback.data or "")
        if index is None or not 0 <= index < len(game.classes):
            await callback.message.answer("Не понял выбор. /new — начать сначала.")
            return
        await offer_subclasses(callback.message, index, gender)

    @router.callback_query(F.data.startswith("s:"))
    async def on_subclass(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.message is None:
            return
        parsed = parse_subclass(callback.data or "")
        gender = await _gender_from(state)
        await callback.answer()
        if parsed is None:
            await callback.message.answer("Не понял выбор. /new — начать сначала.")
            return
        class_index, subclass_index = parsed
        if not 0 <= class_index < len(game.classes):
            await callback.message.answer("Не понял выбор. /new — начать сначала.")
            return
        subclasses = game.subclasses_of(game.classes[class_index])
        if not 0 <= subclass_index < len(subclasses):
            await callback.message.answer("Не понял выбор. /new — начать сначала.")
            return
        await _drop_buttons(callback)
        await state.set_state(Creation.waiting_for_name)
        await state.update_data(class_index=class_index, subclass_index=subclass_index)
        await ask_name(callback.message, class_index, subclass_index, gender)

    @router.callback_query(F.data == SKIP_NAME)
    async def on_skip_name(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.message is None:
            return
        data = await state.get_data()
        await callback.answer()
        await _drop_buttons(callback)
        if "class_index" not in data:
            await callback.message.answer("Создание сорвалось. /new — начать сначала.")
            return
        gender = await _gender_from(state)
        await state.clear()
        # Пустое имя — персонаж будет зваться по своему ремеслу.
        await create_and_start(
            callback.message,
            callback.from_user.id,
            "",
            gender,
            data["class_index"],
            data["subclass_index"],
        )

    @router.message(Creation.waiting_for_name)
    async def on_name(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        name = clean_name(message.text or "")
        if not name:
            await message.answer("Так не пойдёт. Напиши имя словами.")
            return
        data = await state.get_data()
        if "class_index" not in data:
            await state.clear()
            await message.answer("Создание сорвалось. /new — начать сначала.")
            return
        gender = await _gender_from(state)
        await state.clear()
        await create_and_start(
            message, user.id, name, gender, data["class_index"], data["subclass_index"]
        )

    async def _gender_from(state: FSMContext) -> Gender:
        """Пол из незавершённого создания; по умолчанию — мужской."""
        data = await state.get_data()
        try:
            return Gender(data.get("gender", Gender.MALE.value))
        except ValueError:
            return Gender.MALE

    # --- действия в сцене ----------------------------------------------

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
        except SaveOutdated:
            await callback.answer(
                "Сюжет обновился — этот забег продолжить нельзя. Нажми /new",
                show_alert=True,
            )
            return
        except (StaleAction, InvalidAction) as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.answer()
        await edit_turn(callback, turn)

    async def _drop_buttons(callback: CallbackQuery) -> None:
        """Убрать кнопки у отработавшего сообщения, чтобы на них не жали дважды."""
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass

    return router
