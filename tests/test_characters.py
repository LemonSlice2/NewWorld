"""Создание персонажа: пол, класс, специализация, имя.

Проверяется не арифметика, а смысл: каждый выбор должен что-то менять в
игре, иначе конструктор персонажа декоративен.
"""

import random
import re
import textwrap

import pytest

from newworld.bot.app import clean_name
from newworld.core.content import ContentError, Story
from newworld.core.creation import build_character, starting_flags
from newworld.core.engine import Engine
from newworld.core.gendered import both_forms, inflect
from newworld.core.models import Ability, Gender

STORY = """
world:
  title: Мир
  intro: Вводная.

subclasses:
  - id: sledopyt
    name: {m: Следопыт, f: Следопытка}
    tagline: Читает землю
    description: Общее описание следопыта.
    ability_bonus: {dex: 2}
    for_class:
      znahar:
        tagline: Знает лес
        description: Знахарский следопыт.
        ability_bonus: {wis: 1}
        items: [Нож]
        flags: [лесной_следопыт]
      soldat:
        name: {m: Пластун, f: Пластунка}
        description: Солдатский следопыт.
        hp_bonus: 1
        flags: [пластун]
  - id: sheptun
    name: {m: Шептун, f: Шептуха}
    tagline: Говорит словом
    description: Описание шептуна.
    ability_bonus: {cha: 3}
    flags: [шептуха]

classes:
  - id: znahar
    name: {m: Знахарь, f: Знахарка}
    tagline: Старое знание
    description: Ты учил{ся|ась} у матери.
    abilities: {wis: 15, str: 8}
    max_hp: 9
    gold: 3
    items: [Наговор]
    flags: [старое_знание]
    subclasses: [sledopyt, sheptun]
  - id: soldat
    name: {m: Солдат, f: Солдатка}
    tagline: Воевал
    description: Ты воева{л|ла}.
    abilities: {str: 15}
    max_hp: 14
    subclasses: [sledopyt]

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
      - id: сочетание
        label: Только знахарю-следопыту
        requires:
          flags: [старое_знание, лесной_следопыт]
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


# --- согласование по полу --------------------------------------------


@pytest.mark.parametrize(
    "text, male, female",
    [
        ("Ты выш{ел|ла}", "Ты вышел", "Ты вышла"),
        ("не увер{ен|ена}", "не уверен", "не уверена"),
        ("Ты был{|а} там", "Ты был там", "Ты была там"),
        ("без развилок", "без развилок", "без развилок"),
        ("{а|б} и {в|г}", "а и в", "б и г"),
    ],
)
def test_text_agrees_with_gender(text, male, female):
    assert inflect(text, Gender.MALE) == male
    assert inflect(text, Gender.FEMALE) == female
    assert both_forms(text) == (male, female)


def test_class_names_have_both_forms(story):
    znahar = story.character_class("znahar")
    assert znahar.name.for_gender(Gender.MALE) == "Знахарь"
    assert znahar.name.for_gender(Gender.FEMALE) == "Знахарка"


def test_gender_reaches_the_character_and_survives_saving(story):
    from newworld.core.models import Character

    character = build_character("Марфа", Gender.FEMALE, story.character_class("znahar"))
    assert character.gender is Gender.FEMALE
    assert character.origin == "Знахарка"
    assert Character.from_dict(character.to_dict()).gender is Gender.FEMALE


def test_name_without_input_falls_back_to_the_craft_in_right_gender(story):
    znahar = story.character_class("znahar")
    assert build_character("  ", Gender.FEMALE, znahar).name == "Знахарка"
    assert build_character("  ", Gender.MALE, znahar).name == "Знахарь"


# --- общие специализации ---------------------------------------------


def test_one_subclass_can_be_taken_by_several_classes(story):
    """Ради этого специализации и вынесены в общий список."""
    znahar = story.character_class("znahar")
    soldat = story.character_class("soldat")
    assert "sledopyt" in znahar.subclass_ids
    assert "sledopyt" in soldat.subclass_ids


def test_same_subclass_becomes_a_different_thing_in_different_hands(story):
    znahar = story.character_class("znahar")
    soldat = story.character_class("soldat")

    for_znahar = story.subclass_of(znahar, "sledopyt")
    for_soldat = story.subclass_of(soldat, "sledopyt")

    assert for_znahar.name.for_gender(Gender.MALE) == "Следопыт"
    assert for_soldat.name.for_gender(Gender.MALE) == "Пластун"
    assert for_znahar.description == "Знахарский следопыт."
    assert for_soldat.description == "Солдатский следопыт."
    assert for_znahar.flags == ("лесной_следопыт",)
    assert for_soldat.flags == ("пластун",)


def test_class_twist_adds_to_the_base_rather_than_replacing_it(story):
    znahar = story.character_class("znahar")
    sledopyt = story.subclass_of(znahar, "sledopyt")
    # базовая прибавка специализации плюс уточнение для класса
    assert sledopyt.ability_bonus == {Ability.DEX: 2, Ability.WIS: 1}
    assert sledopyt.items == ("Нож",)


def test_subclass_without_twist_keeps_its_base(story):
    znahar = story.character_class("znahar")
    sheptun = story.subclass_of(znahar, "sheptun")
    assert sheptun.name.for_gender(Gender.FEMALE) == "Шептуха"
    assert sheptun.flags == ("шептуха",)


def test_class_cannot_take_a_subclass_it_does_not_have(story):
    with pytest.raises(ContentError, match="не может взять"):
        story.subclass_of(story.character_class("soldat"), "sheptun")


def test_character_sums_class_and_subclass(story):
    znahar = story.character_class("znahar")
    character = build_character(
        "Марфа", Gender.FEMALE, znahar, story.subclass_of(znahar, "sledopyt")
    )
    assert character.origin == "Знахарка · Следопытка"
    assert character.abilities[Ability.WIS] == 16  # 15 от класса + 1 от уточнения
    assert character.abilities[Ability.DEX] == 12  # 10 по умолчанию + 2 от специализации
    assert character.inventory == ["Наговор", "Нож"]


# --- ради чего всё это -----------------------------------------------


def test_the_combination_opens_actions_neither_half_opens_alone(story):
    """Смысл общих специализаций: уникально именно сочетание."""
    engine = Engine(story)

    def options_for(class_id, subclass_id=None):
        character_class = story.character_class(class_id)
        subclass = story.subclass_of(character_class, subclass_id) if subclass_id else None
        turn = engine.start(
            build_character("Имя", Gender.MALE, character_class, subclass),
            seed=1,
            flags=starting_flags(character_class, subclass),
        )
        return {o.id for o in turn.options}

    assert options_for("soldat", "sledopyt") == {"общий"}
    assert options_for("znahar", "sheptun") == {"общий", "классовый"}
    # та же специализация, но у другого класса — и открывается третье действие
    assert options_for("znahar", "sledopyt") == {"общий", "классовый", "сочетание"}


def test_flags_come_from_both_class_and_subclass(story):
    znahar = story.character_class("znahar")
    flags = starting_flags(znahar, story.subclass_of(znahar, "sledopyt"))
    assert flags == ("старое_знание", "лесной_следопыт")


# --- проверки сюжетного файла ----------------------------------------


def test_reference_to_unknown_subclass_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("subclasses: [sledopyt, sheptun]", "subclasses: [нет_такой]"),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="не объявлена"):
        Story.load(path)


def test_twist_for_unknown_class_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("      soldat:\n", "      нет_такого:\n"),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="неизвестного класса"):
        Story.load(path)


def test_name_with_only_one_gender_form_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("name: {m: Знахарь, f: Знахарка}", "name: {m: Знахарь}"),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="не хватает"):
        Story.load(path)


def test_plain_string_name_works_for_both_genders(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace("name: {m: Шептун, f: Шептуха}", "name: Шептун"),
        encoding="utf-8",
    )
    story = Story.load(path)
    assert story.subclasses["sheptun"].name.for_gender(Gender.FEMALE) == "Шептун"


def test_duplicate_subclass_reference_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(STORY).replace(
            "subclasses: [sledopyt, sheptun]", "subclasses: [sledopyt, sledopyt]"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="дважды"):
        Story.load(path)


# --- разбор ввода имени ----------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Марфа", "Марфа"),
        ("  Марфа   Игнатьевна  ", "Марфа Игнатьевна"),
        ("Марфа\nИгнатьевна", "Марфа Игнатьевна"),
        ("   ", ""),
    ],
)
def test_name_input_is_cleaned_up(raw, expected):
    assert clean_name(raw) == expected


def test_overlong_name_is_trimmed():
    assert len(clean_name("Я" * 200)) == 24


# --- демонстрационный сюжет ------------------------------------------


@pytest.fixture(scope="module")
def olhovets():
    return Story.load("content/olhovets.yaml")


def builds(story):
    """Все сочетания класса и специализации в сюжете."""
    for character_class in story.classes:
        for subclass in story.subclasses_of(character_class):
            yield character_class, subclass


def test_demo_story_has_shared_subclasses(olhovets):
    """Хотя бы одна специализация должна быть доступна разным классам —
    иначе общий список не нужен."""
    takers = {
        subclass_id: [c.id for c in olhovets.classes if subclass_id in c.subclass_ids]
        for subclass_id in olhovets.subclasses
    }
    shared = {k: v for k, v in takers.items() if len(v) > 1}
    assert shared, f"ни одна специализация не разделяется классами: {takers}"


def test_every_combination_can_do_something_of_its_own(olhovets):
    """Сочетание, не открывающее ни одного действия, — просто цифры."""
    required = {
        flag
        for scene in olhovets.scenes.values()
        for option in scene.options
        for flag in option.requires.flags
    }
    for character_class, subclass in builds(olhovets):
        assert set(subclass.flags) & required, (
            f"{character_class.name.male} · {subclass.name.male}: флаги "
            f"{subclass.flags} нигде не требуются"
        )


# Формы, в которых виден род: прошедшее время и краткие прилагательные.
# Настоящее время («ты знаешь») рода не показывает, и развилка там не нужна.
GENDERED_FORM = re.compile(
    r"\b[Тт]ы\s+(?:не\s+|уже\s+|ещё\s+)?"
    r"(\w*(?:ал|ял|ел|ил|ул|ыл|нул|шёл|брался|нулся|делся)|увер\w+|готов|должен|рад)\b"
)


def ungendered_places(text: str) -> list[str]:
    """Места, где род виден, но развилки нет."""
    outside_forks = re.sub(r"\{[^{}]*\}", "\u0001", text)
    found = []
    for match in GENDERED_FORM.finditer(outside_forks):
        word = match.group(1)
        if word.endswith(("ешь", "ишь", "ешься", "ишься", "ёшь")):
            continue  # настоящее время, род не виден
        found.append(word)
    return found


def test_no_text_addresses_the_player_in_one_gender_only(olhovets):
    """Русский показывает род в прошедшем времени: «ты вышел» женщине —
    это выбивает из роли, поэтому такие места должны быть с развилкой."""
    problems = []
    for character_class in olhovets.classes:
        for where, text in (
            (character_class.name.male, character_class.description),
            (character_class.name.male + " (строка)", character_class.tagline),
        ):
            for word in ungendered_places(text):
                problems.append(f"{where}: «{word}»")
    for subclass in olhovets.subclasses.values():
        for word in ungendered_places(subclass.description):
            problems.append(f"специализация {subclass.id}: «{word}»")
        for class_id, twist in subclass.for_class.items():
            for word in ungendered_places(twist.description):
                problems.append(f"{subclass.id} у {class_id}: «{word}»")
    for scene in olhovets.scenes.values():
        for text in [scene.text] + [
            branch.text
            for option in scene.options
            for branch in (option.plain, option.on_success, option.on_failure)
        ]:
            for word in ungendered_places(text):
                problems.append(f"сцена {scene.id}: «{word}»")
    assert not problems, "текст обращается к игроку только в одном роде:\n" + "\n".join(problems)


def test_class_names_are_written_for_both_genders(olhovets):
    for character_class in olhovets.classes:
        assert character_class.name.male and character_class.name.female


def play_randomly(engine, character_class, subclass, seed, limit=60):
    turn = engine.start(
        build_character("Тест", Gender.MALE, character_class, subclass),
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
    for character_class, subclass in builds(olhovets):
        finished = any(
            play_randomly(engine, character_class, subclass, seed).scene.ending
            for seed in range(120)
        )
        assert finished, f"{character_class.name.male} · {subclass.name.male} не доходит до конца"


def test_deaths_stay_in_a_reasonable_range(olhovets):
    engine = Engine(olhovets)
    for character_class, subclass in builds(olhovets):
        runs = [play_randomly(engine, character_class, subclass, seed) for seed in range(150)]
        deaths = sum(turn.state.is_over for turn in runs)
        assert deaths / len(runs) < 0.5, (
            f"{character_class.name.male} · {subclass.name.male}: гибнет "
            f"{deaths * 100 // len(runs)}%"
        )
