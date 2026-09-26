"""Создание персонажа: класс, специализация, имя.

Главное, что здесь проверяется, — не арифметика, а смысл: выбор должен
что-то менять в игре, иначе конструктор персонажа декоративен.
"""

import random
import textwrap

import pytest

from newworld.bot.app import clean_name
from newworld.core.content import ContentError, Story
from newworld.core.creation import build_character, starting_flags
from newworld.core.engine import Engine
from newworld.core.models import Ability

STORY = """
world:
  title: Мир
  intro: Вводная.

classes:
  - id: znahar
    name: Знахарь
    tagline: Старое знание
    description: Описание класса.
    abilities: {wis: 15, str: 8}
    max_hp: 9
    gold: 3
    items: [Наговор]
    flags: [старое_знание]
    subclasses:
      - id: travnica
        name: Травница
        tagline: Лечит травами
        description: Описание травницы.
        ability_bonus: {con: 2, wis: 1}
        hp_bonus: 2
        items: [Короб]
        flags: [травница]
      - id: sheptuha
        name: Шептуха
        tagline: Говорит словом
        description: Описание шептухи.
        ability_bonus: {cha: 3}
        flags: [шептуха]
  - id: soldat
    name: Солдат
    tagline: Воевал
    description: Описание солдата.
    abilities: {str: 15}
    max_hp: 14

start: a
scenes:
  - id: a
    title: А
    text: Текст
    options:
      - id: общий
        label: Доступно всем
        goto: b
      - id: классовый
        label: Только знахарю
        requires:
          flags: [старое_знание]
        goto: b
      - id: подклассовый
        label: Только травнице
        requires:
          flags: [травница]
        goto: b
  - id: b
    title: Б
    text: Конец
    ending: true
"""


@pytest.fixture
def story(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(textwrap.dedent(STORY), encoding="utf-8")
    return Story.load(path)


def test_classes_and_subclasses_are_loaded(story):
    assert [c.id for c in story.classes] == ["znahar", "soldat"]
    znahar = story.character_class("znahar")
    assert [s.id for s in znahar.subclasses] == ["travnica", "sheptuha"]
    assert znahar.subclass("travnica").name == "Травница"


def test_unknown_class_and_subclass_are_rejected(story):
    with pytest.raises(ContentError, match="Класс"):
        story.character_class("нет-такого")
    with pytest.raises(ContentError, match="Специализация"):
        story.character_class("znahar").subclass("нет-такой")


def test_subclass_adds_to_the_class_rather_than_replacing_it(story):
    znahar = story.character_class("znahar")
    character = build_character("Марфа", znahar, znahar.subclass("travnica"))

    assert character.name == "Марфа"
    assert character.origin == "Знахарь · Травница"
    assert character.abilities[Ability.WIS] == 16  # 15 от класса + 1 от специализации
    assert character.abilities[Ability.CON] == 12  # 10 по умолчанию + 2
    assert character.abilities[Ability.STR] == 8   # специализация не трогала
    assert character.hp == character.max_hp == 11  # 9 + 2
    assert character.inventory == ["Наговор", "Короб"]
    assert character.gold == 3


def test_class_without_subclass_works_on_its_own(story):
    character = build_character("Иван", story.character_class("soldat"))
    assert character.origin == "Солдат"
    assert character.hp == 14


def test_empty_name_falls_back_to_the_craft(story):
    character = build_character("   ", story.character_class("znahar"))
    assert character.name == "Знахарь"


def test_flags_come_from_both_class_and_subclass(story):
    znahar = story.character_class("znahar")
    assert starting_flags(znahar, znahar.subclass("travnica")) == ("старое_знание", "травница")
    assert starting_flags(story.character_class("soldat")) == ()


def test_each_choice_changes_what_the_hero_can_do(story):
    """Ради этого конструктор и нужен: класс и специализация открывают
    разные действия в одной и той же сцене."""
    engine = Engine(story)
    znahar = story.character_class("znahar")

    def options_for(character_class, subclass=None):
        turn = engine.start(
            build_character("Имя", character_class, subclass),
            seed=1,
            flags=starting_flags(character_class, subclass),
        )
        return {o.id for o in turn.options}

    assert options_for(story.character_class("soldat")) == {"общий"}
    assert options_for(znahar, znahar.subclass("sheptuha")) == {"общий", "классовый"}
    assert options_for(znahar, znahar.subclass("travnica")) == {
        "общий", "классовый", "подклассовый"
    }


def test_character_survives_serialization_with_origin(story):
    from newworld.core.models import Character

    znahar = story.character_class("znahar")
    character = build_character("Марфа", znahar, znahar.subclass("travnica"))
    restored = Character.from_dict(character.to_dict())
    assert restored.origin == "Знахарь · Травница"
    assert restored.abilities == character.abilities


# --- разбор ввода имени ----------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Марфа", "Марфа"),
        ("  Марфа   Игнатьевна  ", "Марфа Игнатьевна"),
        ("Марфа\nИгнатьевна", "Марфа Игнатьевна"),
        ("   ", ""),
        ("", ""),
    ],
)
def test_name_input_is_cleaned_up(raw, expected):
    assert clean_name(raw) == expected


def test_overlong_name_is_trimmed():
    assert len(clean_name("Я" * 200)) == 24


# --- проверки сюжетного файла ----------------------------------------


def test_duplicate_subclass_id_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("id: sheptuha", "id: travnica"), encoding="utf-8"
    )
    with pytest.raises(ContentError, match="объявлен дважды"):
        Story.load(path)


def test_subclass_without_description_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("        description: Описание травницы.\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="description"):
        Story.load(path)


def test_unknown_ability_in_bonus_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("ability_bonus: {cha: 3}", "ability_bonus: {удача: 3}"),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="неизвестная характеристика"):
        Story.load(path)


# --- демонстрационный сюжет ------------------------------------------


@pytest.fixture(scope="module")
def olhovets():
    return Story.load("content/olhovets.yaml")


def test_demo_story_has_classes_with_subclasses(olhovets):
    assert len(olhovets.classes) >= 3
    for character_class in olhovets.classes:
        assert len(character_class.subclasses) >= 2, f"{character_class.name} без специализаций"
        for subclass in character_class.subclasses:
            assert subclass.tagline and subclass.description


def test_every_subclass_can_actually_do_something(olhovets):
    """Специализация, не открывающая ни одного действия, — просто цифры.
    Каждый её флаг должен где-то в сюжете требоваться."""
    required = {
        flag
        for scene in olhovets.scenes.values()
        for option in scene.options
        for flag in option.requires.flags
    }
    for character_class in olhovets.classes:
        for subclass in character_class.subclasses:
            assert set(subclass.flags) & required, (
                f"{character_class.name} · {subclass.name}: флаги {subclass.flags} "
                "нигде не используются — выбор ничего не меняет"
            )


def play_randomly(engine, character_class, subclass, seed, limit=60):
    turn = engine.start(
        build_character("Тест", character_class, subclass),
        seed=seed,
        flags=starting_flags(character_class, subclass),
    )
    rng = random.Random(seed ^ 0x5EED)
    for _ in range(limit):
        if turn.is_over or not turn.options:
            break
        turn = engine.apply(turn.state, rng.choice(turn.options).id)
    return turn


def test_every_build_can_finish_the_story(olhovets):
    engine = Engine(olhovets)
    for character_class in olhovets.classes:
        for subclass in character_class.subclasses:
            finished = any(
                play_randomly(engine, character_class, subclass, seed).scene.ending
                for seed in range(120)
            )
            assert finished, f"{character_class.name} · {subclass.name} не доходит до концовки"


def test_deaths_stay_in_a_reasonable_range(olhovets):
    engine = Engine(olhovets)
    for character_class in olhovets.classes:
        for subclass in character_class.subclasses:
            runs = [
                play_randomly(engine, character_class, subclass, seed) for seed in range(150)
            ]
            deaths = sum(turn.state.is_over for turn in runs)
            assert deaths / len(runs) < 0.5, (
                f"{character_class.name} · {subclass.name}: гибнет "
                f"{deaths * 100 // len(runs)}%"
            )
