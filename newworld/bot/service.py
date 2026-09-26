"""Связка между Telegram и игрой.

Телеграм-слой намеренно тонкий: он умеет только показать текст и принять
нажатие. Всё, что касается правил, живёт в ядре, а этот класс лишь
связывает игрока с его сохранением.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..core.content import CharacterClass, Story, Subclass
from ..core.creation import build_character, roll_character, starting_flags
from ..core.engine import Engine, InvalidAction, Turn
from ..core.events import SceneEntered
from ..core.models import GameState
from ..narrator.base import Narrator
from ..storage import SaveStore


class StaleAction(InvalidAction):
    """Нажата кнопка из устаревшего сообщения."""


class SaveOutdated(Exception):
    """Сохранение не подходит к текущему сюжету.

    Сюжет живёт и меняется: сцену переименовали, историю переписали, к боту
    подключили другой файл. Забег, который ссылается на исчезнувшую сцену,
    продолжить нельзя — но и падать из-за этого бот не должен.
    """


@dataclass
class GameService:
    story_id: str
    story: Story
    engine: Engine
    narrator: Narrator
    store: SaveStore

    @classmethod
    def create(cls, story_id: str, story: Story, narrator: Narrator, store: SaveStore) -> GameService:
        return cls(
            story_id=story_id,
            story=story,
            engine=Engine(story),
            narrator=narrator,
            store=store,
        )

    @property
    def classes(self) -> tuple[CharacterClass, ...]:
        return self.story.classes

    async def start_new(
        self,
        user_id: int,
        name: str,
        character_class: CharacterClass | None = None,
        subclass: Subclass | None = None,
    ) -> Turn:
        """Начать забег. Без класса персонаж бросается случайно."""
        seed = random.SystemRandom().randrange(2**31)
        if character_class is not None:
            character = build_character(name, character_class, subclass)
            flags = starting_flags(character_class, subclass)
        else:
            character = roll_character(name, random.Random(seed))
            flags = ()
        turn = self.engine.start(character, seed=seed, flags=flags)
        await self.store.save(user_id, self.story_id, turn.state)
        return turn

    async def _load_state(self, user_id: int) -> GameState | None:
        """Загрузить сохранение, отбросив несовместимое с текущим сюжетом."""
        saved = await self.store.load(user_id)
        if saved is None:
            return None
        story_id, state = saved
        if story_id != self.story_id or state.scene_id not in self.story.scenes:
            await self.store.delete(user_id)
            raise SaveOutdated(state.scene_id)
        return state

    async def resume(self, user_id: int) -> Turn | None:
        """Восстановить забег и показать текущую сцену без новых событий."""
        state = await self._load_state(user_id)
        if state is None:
            return None
        scene = self.story.scene(state.scene_id)
        return Turn(
            state=state,
            scene=scene,
            events=(SceneEntered(scene_id=scene.id, title=scene.title, first_visit=False),),
            options=self.engine.available_options(state),
            branch_text="",
        )

    async def act(self, user_id: int, expected_turn: int, option_index: int) -> Turn:
        """Выполнить действие по позиции в списке доступных вариантов.

        ``expected_turn`` — номер хода, на котором была нарисована кнопка.
        Если он разошёлся с сохранением, игрок нажал кнопку в прокрученном
        вверх сообщении, и выполнять это действие нельзя: список вариантов
        с тех пор мог смениться целиком.
        """
        state = await self._load_state(user_id)
        if state is None:
            raise StaleAction("Забег не найден — начни новый командой /new")
        if state.turn != expected_turn:
            raise StaleAction("Это кнопка из старого сообщения")
        options = self.engine.available_options(state)
        if not 0 <= option_index < len(options):
            raise StaleAction("Такого варианта больше нет")
        turn = self.engine.apply(state, options[option_index].id)
        await self.store.save(user_id, self.story_id, turn.state)
        return turn

    async def abandon(self, user_id: int) -> None:
        await self.store.delete(user_id)
