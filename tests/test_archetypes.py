"""Персонажи: загрузка, создание и то, ради чего они нужны, —
разные герои видят в одной сцене разные действия."""

import random
import textwrap

import pytest

from newworld.core.content import ContentError, Story
from newworld.core.creation import character_from_archetype
from newworld.core.engine import Engine
from newworld.core.models import Ability

STORY = """
world:
  title: Мир
  intro: |
    Первая строка.
    Вторая строка.

archetypes:
  - id: ведун
    name: Ведун
    tagline: Знает старое
    description: Описание ведуна.
    abilities: {wis: 16, str: 8}
    max_hp: 9
    gold: 3
    items: [Оберег]
    flags: [старое_знание]
  - id: солдат
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
      - id: особый
        label: Только для ведуна
        requires:
          flags: [старое_знание]
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


def test_world_intro_is_loaded_and_normalized(story):
    assert story.world_title == "Мир"
    assert story.world_intro == "Первая строка. Вторая строка."


def test_archetypes_are_loaded_in_order(story):
    assert [a.id for a in story.archetypes] == ["ведун", "солдат"]
    assert story.archetype("ведун").name == "Ведун"


def test_unknown_archetype_is_rejected(story):
    with pytest.raises(ContentError, match="не найден"):
        story.archetype("нет-такого")


def test_character_gets_archetype_numbers_and_kit(story):
    character = character_from_archetype(story.archetype("ведун"))
    assert character.name == "Ведун"
    assert character.abilities[Ability.WIS] == 16
    assert character.abilities[Ability.STR] == 8
    assert character.abilities[Ability.DEX] == 10  # не указана — среднее значение
    assert character.hp == character.max_hp == 9
    assert character.gold == 3
    assert character.inventory == ["Оберег"]


def test_starting_flags_open_options_for_one_hero_only(story):
    """Ради этого архетипы и существуют: свой герой — свои действия."""
    engine = Engine(story)

    veduny = engine.start(
        character_from_archetype(story.archetype("ведун")),
        seed=1,
        flags=story.archetype("ведун").flags,
    )
    soldier = engine.start(
        character_from_archetype(story.archetype("солдат")),
        seed=1,
        flags=story.archetype("солдат").flags,
    )

    assert {o.id for o in veduny.options} == {"общий", "особый"}
    assert {o.id for o in soldier.options} == {"общий"}


def test_archetype_without_flags_starts_clean(story):
    engine = Engine(story)
    turn = engine.start(character_from_archetype(story.archetype("солдат")), seed=1)
    assert turn.state.flags == set()


def test_duplicate_archetype_id_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("id: солдат", "id: ведун"), encoding="utf-8"
    )
    with pytest.raises(ContentError, match="объявлен дважды"):
        Story.load(path)


def test_archetype_with_unknown_ability_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("abilities: {wis: 16, str: 8}", "abilities: {удача: 16}"),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="неизвестная характеристика"):
        Story.load(path)


def test_archetype_without_description_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("    description: Описание ведуна.\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="description"):
        Story.load(path)


# --- демонстрационный сюжет ------------------------------------------


@pytest.fixture(scope="module")
def olhovets():
    return Story.load("content/olhovets.yaml")


def test_demo_story_offers_heroes_and_a_world(olhovets):
    assert olhovets.world_intro
    assert len(olhovets.archetypes) >= 3
    for archetype in olhovets.archetypes:
        assert archetype.tagline and archetype.description


def play_randomly(engine, archetype, seed, limit=60):
    turn = engine.start(
        character_from_archetype(archetype), seed=seed, flags=archetype.flags
    )
    rng = random.Random(seed ^ 0x5EED)
    for _ in range(limit):
        if turn.is_over or not turn.options:
            break
        turn = engine.apply(turn.state, rng.choice(turn.options).id)
    return turn


def test_every_hero_can_finish_the_demo_story(olhovets):
    """Ни один персонаж не должен застревать без выхода."""
    engine = Engine(olhovets)
    for archetype in olhovets.archetypes:
        finished = any(
            play_randomly(engine, archetype, seed).scene.ending for seed in range(120)
        )
        assert finished, f"{archetype.name} не доходит ни до одной концовки"


def test_deaths_stay_in_a_reasonable_range(olhovets):
    """Случайная игра не должна убивать чаще, чем в половине забегов:
    иначе игрок не успевает понять правила."""
    engine = Engine(olhovets)
    for archetype in olhovets.archetypes:
        runs = [play_randomly(engine, archetype, seed) for seed in range(200)]
        deaths = sum(turn.state.is_over for turn in runs)
        assert deaths / len(runs) < 0.5, f"{archetype.name}: гибнет {deaths / 2:.0f}%"


def test_healing_exists_somewhere_in_the_story(olhovets):
    """Раненому игроку должно быть где восстановиться."""
    heals = [
        effect
        for scene in olhovets.scenes.values()
        for option in scene.options
        for branch in (option.plain, option.on_success, option.on_failure)
        for effect in branch.effects
        if effect.type == "heal"
    ]
    assert heals, "в сюжете негде вылечиться"
