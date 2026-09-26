"""Движок: превращает действие игрока в факты о случившемся.

Это единственное место, где меняется состояние игры. Движок ничего не
рассказывает — он возвращает список событий, а описывать их словами будет
рассказчик. Благодаря этому правила остаются проверяемыми, а текст можно
менять (хоть на нейросетевой) не трогая логику.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

from .content import Branch, Effect, Option, Requirement, Scene, Story
from .dice import CheckResult, check
from .events import (
    CheckRolled,
    DamageTaken,
    Died,
    Event,
    FlagSet,
    GoldChanged,
    Healed,
    ItemGained,
    ItemLost,
    SceneEntered,
)
from .models import Character, GameState


class InvalidAction(ValueError):
    """Игрок прислал действие, недоступное в текущей сцене."""


@dataclass
class Turn:
    """Результат одного хода: новое состояние, что произошло, что дальше."""

    state: GameState
    scene: Scene
    events: tuple[Event, ...]
    options: tuple[Option, ...]
    # Авторский текст выбранной ветки. Рассказчик волен его использовать
    # как есть или переписать своими словами.
    branch_text: str = ""

    @property
    def is_over(self) -> bool:
        return self.state.is_over or self.scene.ending


class Engine:
    """Правила игры поверх загруженного сюжета."""

    def __init__(self, story: Story) -> None:
        self.story = story

    # --- запуск -------------------------------------------------------

    def start(
        self,
        character: Character,
        seed: int | None = None,
        flags: Iterable[str] = (),
    ) -> Turn:
        """Начать забег. Без сида берётся случайный — он сохраняется в состоянии.

        ``flags`` — стартовые метки персонажа: они открывают в сценах
        действия, доступные именно такому герою.
        """
        if seed is None:
            seed = random.SystemRandom().randrange(2**31)
        state = GameState(
            character=character,
            scene_id=self.story.start_scene,
            seed=seed,
            flags=set(flags),
        )
        scene = self.story.scene(state.scene_id)
        first_visit = scene.id not in state.visited
        state.visited.add(scene.id)
        events: tuple[Event, ...] = (
            SceneEntered(scene_id=scene.id, title=scene.title, first_visit=first_visit),
        )
        return Turn(
            state=state,
            scene=scene,
            events=events,
            options=self.available_options(state),
            branch_text="",
        )

    # --- доступность действий -----------------------------------------

    def _meets(self, state: GameState, requires: Requirement) -> bool:
        if requires.is_empty:
            return True
        character = state.character
        if any(flag not in state.flags for flag in requires.flags):
            return False
        if any(flag in state.flags for flag in requires.not_flags):
            return False
        if any(item not in character.inventory for item in requires.items):
            return False
        if character.gold < requires.min_gold:
            return False
        return True

    def available_options(self, state: GameState) -> tuple[Option, ...]:
        """Варианты, доступные игроку прямо сейчас."""
        if state.is_over:
            return ()
        scene = self.story.scene(state.scene_id)
        return tuple(o for o in scene.options if self._meets(state, o.requires))

    # --- ход ----------------------------------------------------------

    def _rng(self, state: GameState) -> random.Random:
        """Генератор на этот ход.

        Он выводится из сида забега и номера хода, поэтому не нужно хранить
        внутреннее состояние ГСЧ между ходами, а забег полностью
        воспроизводится по (seed, последовательность выборов).
        """
        return random.Random(state.seed * 1_000_003 + state.turn)

    def apply(self, state: GameState, option_id: str) -> Turn:
        """Выполнить действие игрока. Состояние меняется на месте."""
        if state.is_over:
            raise InvalidAction("Забег окончен")
        scene = self.story.scene(state.scene_id)
        options = self.available_options(state)
        option = next((o for o in options if o.id == option_id), None)
        if option is None:
            known = ", ".join(o.id for o in options) or "нет доступных действий"
            raise InvalidAction(f"Действие {option_id!r} недоступно в сцене {scene.id!r}. Доступны: {known}")

        events: list[Event] = []
        rng = self._rng(state)
        state.turn += 1

        if option.check is not None:
            bonus = state.character.modifier_for(option.check.ability)
            result: CheckResult = check(option.check.dc, rng, bonus=bonus)
            events.append(CheckRolled(ability=option.check.ability, result=result))
            branch = option.on_success if result.is_success else option.on_failure
        else:
            branch = option.plain

        events.extend(self._apply_effects(state, branch))

        if not state.character.is_alive:
            events.append(Died())
            next_scene = scene
        else:
            next_scene = self._go(state, branch, scene, events)

        return Turn(
            state=state,
            scene=next_scene,
            events=tuple(events),
            options=self.available_options(state),
            branch_text=branch.text,
        )

    def _go(self, state: GameState, branch: Branch, current: Scene, events: list[Event]) -> Scene:
        if branch.goto is None:
            return current
        target = self.story.scene(branch.goto)
        state.scene_id = target.id
        first_visit = target.id not in state.visited
        state.visited.add(target.id)
        events.append(SceneEntered(scene_id=target.id, title=target.title, first_visit=first_visit))
        return target

    def _apply_effects(self, state: GameState, branch: Branch) -> list[Event]:
        events: list[Event] = []
        character = state.character
        for effect in branch.effects:
            events.extend(self._apply_effect(state, character, effect))
        return events

    def _apply_effect(self, state: GameState, character: Character, effect: Effect) -> list[Event]:
        if effect.type == "damage":
            dealt = character.take_damage(effect.amount)
            return [DamageTaken(amount=dealt)] if dealt else []
        if effect.type == "heal":
            healed = character.heal(effect.amount)
            return [Healed(amount=healed)] if healed else []
        if effect.type == "gold":
            # Не даём уйти в минус: тратить можно только то, что есть.
            delta = max(effect.amount, -character.gold)
            character.gold += delta
            return [GoldChanged(amount=delta)] if delta else []
        if effect.type == "item_gain":
            character.inventory.append(effect.value)
            return [ItemGained(item=effect.value)]
        if effect.type == "item_lose":
            if effect.value in character.inventory:
                character.inventory.remove(effect.value)
                return [ItemLost(item=effect.value)]
            return []
        if effect.type == "flag":
            if effect.value not in state.flags:
                state.flags.add(effect.value)
                return [FlagSet(flag=effect.value)]
            return []
        raise AssertionError(f"Необработанный эффект {effect.type!r} — проверь content.EFFECT_TYPES")
