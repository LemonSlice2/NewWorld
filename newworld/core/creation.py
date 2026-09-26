"""Создание персонажа."""

from __future__ import annotations

import random

from .content import Archetype
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


def character_from_archetype(archetype: Archetype) -> Character:
    """Готовый герой из сюжетного файла.

    Характеристики заданы автором, а не случаем: игрок должен понимать, кем
    он играет, ещё до первой сцены.
    """
    return Character(
        name=archetype.name,
        abilities=dict(archetype.abilities),
        hp=archetype.max_hp,
        max_hp=archetype.max_hp,
        gold=archetype.gold,
        inventory=list(archetype.items),
    )
