"""События — то, что движок сообщает о случившемся.

Ход игрока превращается в список событий: «кинули проверку», «получили
предмет», «потеряли хиты». Рассказчик (шаблонный или нейросетевой) читает
этот список и описывает его словами. Он ничего не решает — только излагает.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dice import CheckResult
from .models import Ability


@dataclass(frozen=True)
class Event:
    """Базовое событие. Наследники добавляют поля."""


@dataclass(frozen=True)
class SceneEntered(Event):
    scene_id: str
    title: str
    first_visit: bool


@dataclass(frozen=True)
class CheckRolled(Event):
    ability: Ability
    result: CheckResult


@dataclass(frozen=True)
class DamageTaken(Event):
    amount: int
    source: str | None = None


@dataclass(frozen=True)
class Healed(Event):
    amount: int


@dataclass(frozen=True)
class ItemGained(Event):
    item: str


@dataclass(frozen=True)
class ItemLost(Event):
    item: str


@dataclass(frozen=True)
class GoldChanged(Event):
    amount: int


@dataclass(frozen=True)
class FlagSet(Event):
    flag: str


@dataclass(frozen=True)
class Died(Event):
    reason: str | None = None
