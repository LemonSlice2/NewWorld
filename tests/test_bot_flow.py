"""Сквозная проверка бота: от /start до хода в игре.

Обычные тесты проверяют ядро и сервис, но между ними и игроком лежит
целый слой — обработчики, клавиатуры, состояния. Здесь через настоящий
Dispatcher прогоняется тот же путь, что проходит живой человек, а вместо
сети стоит заглушка. Если хоть один шаг перестанет отвечать, это видно
сразу, а не в переписке с игроком.
"""

import datetime as dt
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User

from newworld.bot.app import build_router
from newworld.bot.health_bar import HealthBarImages
from newworld.bot.service import GameService
from newworld.core.content import Story
from newworld.narrator import TemplateNarrator
from newworld.storage import SaveStore

USER = User(id=777, is_bot=False, first_name="Коля")
CHAT = Chat(id=777, type="private")
NOW = dt.datetime(2029, 8, 14, 20, 0)


class RecordingSession(BaseSession):
    """Вместо Telegram — список того, что бот попытался отправить."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1000

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - не используется
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self._next_id += 1
        data = method.model_dump()
        self.calls.append((name, data))
        if name in ("SendMessage", "EditMessageText", "EditMessageReplyMarkup"):
            return Message(
                message_id=self._next_id, date=NOW, chat=CHAT, text=data.get("text") or "x"
            )
        if name == "SendPhoto":
            return Message(
                message_id=self._next_id,
                date=NOW,
                chat=CHAT,
                caption=data.get("caption"),
                photo=[
                    PhotoSize(
                        file_id="file-id", file_unique_id="u", width=660, height=103, file_size=1
                    )
                ],
            )
        if name == "GetMe":
            return User(id=1, is_bot=True, first_name="bot", username="b")
        return True

    # --- удобства для проверок ---------------------------------------

    def since(self, mark: int) -> list[tuple[str, dict[str, Any]]]:
        return self.calls[mark:]

    def texts_since(self, mark: int) -> str:
        return "\n".join(
            (data.get("text") or data.get("caption") or "") for _, data in self.since(mark)
        )


class BotUnderTest:
    def __init__(self, session: RecordingSession, dispatcher: Dispatcher, bot: Bot) -> None:
        self.session = session
        self.dispatcher = dispatcher
        self.bot = bot
        self._update_id = 0

    def _next(self) -> int:
        self._update_id += 1
        return self._update_id

    async def send(self, text: str) -> list[tuple[str, dict[str, Any]]]:
        mark = len(self.session.calls)
        update = Update(
            update_id=self._next(),
            message=Message(
                message_id=self._next(), date=NOW, chat=CHAT, from_user=USER, text=text
            ),
        )
        await self.dispatcher.feed_update(self.bot, update)
        return self.session.since(mark)

    async def press(self, data: str) -> list[tuple[str, dict[str, Any]]]:
        mark = len(self.session.calls)
        update = Update(
            update_id=self._next(),
            callback_query=CallbackQuery(
                id=str(self._next()),
                from_user=USER,
                chat_instance="ci",
                data=data,
                message=Message(message_id=self._next(), date=NOW, chat=CHAT, text="сцена"),
            ),
        )
        await self.dispatcher.feed_update(self.bot, update)
        return self.session.since(mark)

    def buttons(self) -> list[str]:
        """Данные кнопок из последнего отправленного сообщения."""
        for _, data in reversed(self.session.calls):
            markup = data.get("reply_markup")
            if markup:
                rows = markup["inline_keyboard"] if isinstance(markup, dict) else markup.inline_keyboard
                return [
                    (b["callback_data"] if isinstance(b, dict) else b.callback_data)
                    for row in rows
                    for b in row
                ]
        return []


@pytest.fixture
def bot(tmp_path):
    story = Story.load("content/olhovets.yaml")
    game = GameService.create(
        story_id="olhovets",
        story=story,
        narrator=TemplateNarrator(),
        store=SaveStore(tmp_path / "saves.db"),
    )
    session = RecordingSession()
    telegram = Bot("123:FAKE", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(game, HealthBarImages()))
    return BotUnderTest(session, dispatcher, telegram)


def kinds(calls) -> list[str]:
    return [name for name, _ in calls]


@pytest.mark.asyncio
async def test_start_offers_the_world_and_a_choice(bot):
    calls = await bot.send("/start")
    assert kinds(calls).count("SendMessage") == 3  # справка, мир, выбор пола
    assert "Кто пойдёт" in bot.session.texts_since(0)
    assert bot.buttons() == ["g:m", "g:f"]


@pytest.mark.asyncio
async def test_whole_creation_leads_to_the_first_scene(bot):
    await bot.send("/start")

    await bot.press("g:f")
    assert "была" in bot.session.texts_since(0), "текст не согласован по полу"
    assert bot.buttons() == ["c:0", "c:1", "c:2"]

    await bot.press("c:0")
    assert bot.buttons()[-1] == "c:back"

    mark = len(bot.session.calls)
    await bot.press("s:0:0")
    assert "Как её зовут" in bot.session.texts_since(mark)

    mark = len(bot.session.calls)
    await bot.send("Марфа")
    text = bot.session.texts_since(mark)
    assert "Марфа" in text and "Знахарка" in text
    assert "Гать через болото" in text, "не дошли до первой сцены"


@pytest.mark.asyncio
async def test_actions_redraw_the_scene_instead_of_spamming(bot):
    await bot.send("/start")
    await bot.press("g:m")
    await bot.press("c:2")
    await bot.press("s:2:0")
    await bot.send("Семён")

    calls = await bot.press("a:0:0")
    assert kinds(calls) == ["AnswerCallbackQuery", "EditMessageText"], (
        "ход должен перерисовывать сообщение, а не слать новое"
    )


@pytest.mark.asyncio
async def test_stale_button_is_refused_with_an_alert(bot):
    await bot.send("/start")
    await bot.press("g:m")
    await bot.press("c:2")
    await bot.press("s:2:0")
    await bot.send("Семён")
    await bot.press("a:0:0")

    calls = await bot.press("a:0:0")  # та же кнопка второй раз
    assert kinds(calls) == ["AnswerCallbackQuery"]
    assert calls[0][1].get("show_alert") is True


@pytest.mark.asyncio
async def test_status_sends_the_health_picture(bot):
    await bot.send("/start")
    await bot.press("g:f")
    await bot.press("c:0")
    await bot.press("s:0:0")
    await bot.send("Марфа")

    calls = await bot.send("/status")
    assert kinds(calls) == ["SendPhoto"], "карточка должна уходить картинкой"
    caption = calls[0][1]["caption"]
    assert "Марфа" in caption and len(caption) < 1024


@pytest.mark.asyncio
async def test_status_reuses_the_uploaded_picture(bot):
    await bot.send("/start")
    await bot.press("g:f")
    await bot.press("c:0")
    await bot.press("s:0:0")
    await bot.send("Марфа")

    first = await bot.send("/status")
    second = await bot.send("/status")
    assert isinstance(second[0][1]["photo"], str), (
        "вторая отправка должна ссылаться на уже загруженный файл"
    )
    assert first[0][1]["photo"] != second[0][1]["photo"]


@pytest.mark.asyncio
async def test_help_and_status_work_before_any_run(bot):
    assert kinds(await bot.send("/help")) == ["SendMessage"]
    calls = await bot.send("/status")
    assert "не начат" in (calls[0][1].get("text") or "")


@pytest.mark.asyncio
async def test_new_restarts_creation(bot):
    await bot.send("/start")
    await bot.press("g:m")
    await bot.press("c:1")
    await bot.press("s:1:0")
    await bot.send("Иван")

    mark = len(bot.session.calls)
    await bot.send("/new")
    assert "Кто пойдёт" in bot.session.texts_since(mark)
    assert bot.buttons() == ["g:m", "g:f"]


@pytest.mark.asyncio
async def test_garbage_button_does_not_break_the_bot(bot):
    await bot.send("/start")
    for junk in ("c:999", "s:9:9", "g:x", "a:зз:0"):
        calls = await bot.press(junk)
        assert calls, f"на {junk} бот промолчал"
