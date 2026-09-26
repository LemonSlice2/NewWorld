"""Создание персонажа."""

from __future__ import annotations

import random

from .content import CharacterClass, Subclass
from .models import Ability, Character, Gender


def roll_character(name: str, rng: random.Random, gender: Gender = Gender.MALE) -> Character:
    """Случайный персонаж: 4d6 на характеристику, худшая кость отбрасывается.

    Используется там, где сюжет не предлагает классов.
    """
    abilities: dict[Ability, int] = {}
    for ability in Ability:
        dice = sorted(rng.randint(1, 6) for _ in range(4))
        abilities[ability] = sum(dice[1:])
    max_hp = 8 + (abilities[Ability.CON] - 10) // 2
    return Character(name=name, gender=gender, abilities=abilities, hp=max_hp, max_hp=max_hp)


def build_character(
    name: str,
    gender: Gender,
    character_class: CharacterClass,
    subclass: Subclass | None = None,
) -> Character:
    """Собрать героя: имя и пол от игрока, остальное — от класса и выучки.

    Специализация не переписывает класс, а уточняет его: прибавки
    складываются с классовыми, вещи добавляются к классовым. Ожидается
    специализация, уже приведённая к этому классу (``resolved_for``).
    """
    abilities = dict(character_class.abilities)
    max_hp = character_class.max_hp
    items = list(character_class.items)
    class_name = character_class.name.for_gender(gender)
    origin = class_name

    if subclass is not None:
        for ability, bonus in subclass.ability_bonus.items():
            abilities[ability] = abilities.get(ability, 10) + bonus
        max_hp += subclass.hp_bonus
        items.extend(subclass.items)
        origin = f"{class_name} · {subclass.name.for_gender(gender)}"

    return Character(
        name=name.strip() or class_name,
        origin=origin,
        gender=gender,
        abilities=abilities,
        hp=max_hp,
        max_hp=max_hp,
        gold=character_class.gold,
        inventory=items,
    )


def starting_flags(
    character_class: CharacterClass, subclass: Subclass | None = None
) -> tuple[str, ...]:
    """Метки, с которыми герой выходит в мир.

    Флаги класса и специализации складываются, поэтому сцена может
    требовать их вместе — и тогда действие достанется только конкретному
    сочетанию, а не всякому, кто взял эту выучку.
    """
    flags = list(character_class.flags)
    if subclass is not None:
        flags.extend(subclass.flags)
    return tuple(flags)
