"""Состояние игры: персонаж и мир.

Здесь нет ни текста, ни Telegram, ни нейросети — только факты. Всё, что
можно проверить и посчитать, живёт в этом модуле; всё, что нужно красиво
описать, берёт эти факты и превращает в текст уже слоем выше.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Ability(str, Enum):
    STR = "str"
    DEX = "dex"
    CON = "con"
    INT = "int"
    WIS = "wis"
    CHA = "cha"

    @property
    def label(self) -> str:
        return _ABILITY_LABELS[self]


_ABILITY_LABELS = {
    Ability.STR: "Сила",
    Ability.DEX: "Ловкость",
    Ability.CON: "Телосложение",
    Ability.INT: "Интеллект",
    Ability.WIS: "Мудрость",
    Ability.CHA: "Харизма",
}

DEFAULT_ABILITIES = {ability: 10 for ability in Ability}


def modifier(score: int) -> int:
    """Модификатор характеристики: 10-11 дают 0, дальше по +1 за каждые два."""
    return (score - 10) // 2


@dataclass
class Character:
    name: str
    abilities: dict[Ability, int] = field(default_factory=lambda: dict(DEFAULT_ABILITIES))
    hp: int = 10
    max_hp: int = 10
    gold: int = 0
    inventory: list[str] = field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def modifier_for(self, ability: Ability) -> int:
        return modifier(self.abilities.get(ability, 10))

    def take_damage(self, amount: int) -> int:
        """Нанести урон. Возвращает фактически снятые хиты."""
        amount = max(0, amount)
        dealt = min(amount, self.hp)
        self.hp -= dealt
        return dealt

    def heal(self, amount: int) -> int:
        """Вылечить. Возвращает фактически восстановленные хиты."""
        amount = max(0, amount)
        healed = min(amount, self.max_hp - self.hp)
        self.hp += healed
        return healed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "abilities": {a.value: v for a, v in self.abilities.items()},
            "hp": self.hp,
            "max_hp": self.max_hp,
            "gold": self.gold,
            "inventory": list(self.inventory),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Character:
        abilities = dict(DEFAULT_ABILITIES)
        abilities.update({Ability(k): v for k, v in data.get("abilities", {}).items()})
        return cls(
            name=data["name"],
            abilities=abilities,
            hp=data.get("hp", 10),
            max_hp=data.get("max_hp", 10),
            gold=data.get("gold", 0),
            inventory=list(data.get("inventory", [])),
        )


@dataclass
class GameState:
    """Полный снимок забега. Всё, что нужно, чтобы продолжить игру."""

    character: Character
    scene_id: str
    seed: int
    turn: int = 0
    flags: set[str] = field(default_factory=set)
    visited: set[str] = field(default_factory=set)

    @property
    def is_over(self) -> bool:
        return not self.character.is_alive

    def to_dict(self) -> dict[str, Any]:
        return {
            "character": self.character.to_dict(),
            "scene_id": self.scene_id,
            "seed": self.seed,
            "turn": self.turn,
            "flags": sorted(self.flags),
            "visited": sorted(self.visited),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameState:
        return cls(
            character=Character.from_dict(data["character"]),
            scene_id=data["scene_id"],
            seed=data["seed"],
            turn=data.get("turn", 0),
            flags=set(data.get("flags", [])),
            visited=set(data.get("visited", [])),
        )
