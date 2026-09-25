"""Создание персонажа."""

from __future__ import annotations

import random

from .models import Ability, Character


def roll_character(name: str, rng: random.Random) -> Character:
    """Классическая генерация: 4d6 на характеристику, худшая кость отбрасывается.

    Такой бросок даёт в среднем около 12 при разбросе 3-18 — персонажи выходят
    разными, но почти никогда безнадёжными.
    """
    abilities: dict[Ability, int] = {}
    for ability in Ability:
        dice = sorted(rng.randint(1, 6) for _ in range(4))
        abilities[ability] = sum(dice[1:])
    max_hp = 8 + (abilities[Ability.CON] - 10) // 2
    return Character(name=name, abilities=abilities, hp=max_hp, max_hp=max_hp)
