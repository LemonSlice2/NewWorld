"""Создание персонажа."""

from __future__ import annotations

import random

from .content import CharacterClass, Subclass
from .models import Ability, Character


def roll_character(name: str, rng: random.Random) -> Character:
    """Случайный персонаж: 4d6 на характеристику, худшая кость отбрасывается.

    Такой бросок даёт в среднем около 12 при разбросе 3-18 — персонажи выходят
    разными, но почти никогда безнадёжными. Используется там, где сюжет не
    предлагает готовых героев.
    """
    abilities: dict[Ability, int] = {}
    for ability in Ability:
        dice = sorted(rng.randint(1, 6) for _ in range(4))
        abilities[ability] = sum(dice[1:])
    max_hp = 8 + (abilities[Ability.CON] - 10) // 2
    return Character(name=name, abilities=abilities, hp=max_hp, max_hp=max_hp)


def build_character(
    name: str,
    character_class: CharacterClass,
    subclass: Subclass | None = None,
) -> Character:
    """Собрать героя: имя от игрока, всё остальное — от класса и специализации.

    Подкласс не переписывает класс, а уточняет его: прибавляет к
    характеристикам, добавляет вещь и своё снаряжение.
    """
    abilities = dict(character_class.abilities)
    max_hp = character_class.max_hp
    items = list(character_class.items)
    origin = character_class.name

    if subclass is not None:
        for ability, bonus in subclass.ability_bonus.items():
            abilities[ability] = abilities.get(ability, 10) + bonus
        max_hp += subclass.hp_bonus
        items.extend(subclass.items)
        origin = f"{character_class.name} · {subclass.name}"

    return Character(
        name=name.strip() or character_class.name,
        origin=origin,
        abilities=abilities,
        hp=max_hp,
        max_hp=max_hp,
        gold=character_class.gold,
        inventory=items,
    )


def starting_flags(
    character_class: CharacterClass, subclass: Subclass | None = None
) -> tuple[str, ...]:
    """Метки, с которыми герой выходит в мир: от класса и от специализации."""
    flags = list(character_class.flags)
    if subclass is not None:
        flags.extend(subclass.flags)
    return tuple(flags)
