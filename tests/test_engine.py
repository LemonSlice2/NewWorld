import random
import textwrap

import pytest

from newworld.core.content import Story
from newworld.core.engine import Engine, InvalidAction
from newworld.core.events import DamageTaken, Died, GoldChanged, ItemGained, SceneEntered
from newworld.core.models import Ability, Character

STORY = """
start: hub
scenes:
  - id: hub
    title: Развилка
    text: Текст
    options:
      - id: loot
        label: Взять
        text: Взял
        effects:
          - type: item_gain
            value: Фонарь
          - type: gold
            amount: 10
          - type: flag
            value: обыскал
      - id: spend
        label: Потратить 100
        effects:
          - type: gold
            amount: -100
      - id: hurt
        label: Пораниться
        effects:
          - type: damage
            amount: 3
      - id: kill
        label: Умереть
        effects:
          - type: damage
            amount: 999
      - id: locked
        label: Только с фонарём
        requires:
          items: [Фонарь]
        goto: done
      - id: rich
        label: Только с деньгами
        requires:
          min_gold: 5
        goto: done
      - id: once
        label: Только до обыска
        requires:
          not_flags: [обыскал]
        goto: done
      - id: risky
        label: Рискнуть
        check:
          ability: dex
          dc: 10
        on_success:
          text: Вышло
          effects:
            - type: heal
              amount: 2
        on_failure:
          text: Не вышло
          effects:
            - type: damage
              amount: 2
  - id: done
    title: Финал
    text: Всё
    ending: true
"""


@pytest.fixture
def story(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(textwrap.dedent(STORY), encoding="utf-8")
    return Story.load(path)


@pytest.fixture
def engine(story):
    return Engine(story)


def make_character(**kwargs):
    defaults = dict(
        name="Тест",
        abilities={a: 10 for a in Ability},
        hp=10,
        max_hp=10,
    )
    defaults.update(kwargs)
    return Character(**defaults)


def option_ids(turn):
    return {o.id for o in turn.options}


def test_start_enters_first_scene(engine):
    turn = engine.start(make_character(), seed=1)
    assert turn.scene.id == "hub"
    assert any(isinstance(e, SceneEntered) for e in turn.events)
    assert turn.state.turn == 0


def test_effects_are_applied_and_reported(engine):
    turn = engine.start(make_character(), seed=1)
    turn = engine.apply(turn.state, "loot")
    assert turn.state.character.inventory == ["Фонарь"]
    assert turn.state.character.gold == 10
    assert "обыскал" in turn.state.flags
    assert any(isinstance(e, ItemGained) for e in turn.events)
    assert any(isinstance(e, GoldChanged) for e in turn.events)


def test_gold_never_goes_negative(engine):
    turn = engine.start(make_character(), seed=1)
    turn = engine.apply(turn.state, "spend")
    assert turn.state.character.gold == 0


def test_damage_produces_event_and_lowers_hp(engine):
    turn = engine.start(make_character(), seed=1)
    turn = engine.apply(turn.state, "hurt")
    assert turn.state.character.hp == 7
    assert any(isinstance(e, DamageTaken) and e.amount == 3 for e in turn.events)


def test_death_ends_the_run(engine):
    turn = engine.start(make_character(), seed=1)
    turn = engine.apply(turn.state, "kill")
    assert turn.state.is_over
    assert any(isinstance(e, Died) for e in turn.events)
    assert turn.options == ()
    with pytest.raises(InvalidAction):
        engine.apply(turn.state, "loot")


def test_requires_hides_and_reveals_options(engine):
    turn = engine.start(make_character(), seed=1)
    assert "locked" not in option_ids(turn)
    assert "rich" not in option_ids(turn)
    assert "once" in option_ids(turn)

    turn = engine.apply(turn.state, "loot")
    assert "locked" in option_ids(turn)  # появился фонарь
    assert "rich" in option_ids(turn)  # появились деньги
    assert "once" not in option_ids(turn)  # флаг закрыл вариант


def test_unavailable_option_is_rejected(engine):
    turn = engine.start(make_character(), seed=1)
    with pytest.raises(InvalidAction, match="недоступно"):
        engine.apply(turn.state, "locked")
    with pytest.raises(InvalidAction):
        engine.apply(turn.state, "такого-нет")


def test_check_branches_diverge_by_outcome(engine):
    """Одна и та же кнопка при разных сидах даёт разные ветки."""
    seen = set()
    for seed in range(40):
        turn = engine.start(make_character(hp=5), seed=seed)
        turn = engine.apply(turn.state, "risky")
        seen.add(turn.branch_text)
    assert seen == {"Вышло", "Не вышло"}


def test_same_seed_reproduces_the_same_run(engine):
    def play(seed):
        turn = engine.start(make_character(), seed=seed)
        for _ in range(5):
            turn = engine.apply(turn.state, "risky")
        return turn.state.character.hp

    assert play(1234) == play(1234)


def test_ability_modifier_shifts_the_odds(engine):
    """Высокая ловкость должна давать заметно больше успехов."""

    def successes(dex):
        count = 0
        for seed in range(60):
            turn = engine.start(make_character(abilities={**{a: 10 for a in Ability}, Ability.DEX: dex}), seed=seed)
            turn = engine.apply(turn.state, "risky")
            count += turn.branch_text == "Вышло"
        return count

    assert successes(18) > successes(4)


def test_goto_moves_to_new_scene(engine):
    turn = engine.start(make_character(), seed=1)
    turn = engine.apply(turn.state, "loot")
    turn = engine.apply(turn.state, "locked")
    assert turn.scene.id == "done"
    assert turn.is_over  # сцена помечена как концовка


def test_state_survives_serialization(engine):
    from newworld.core.models import GameState

    turn = engine.start(make_character(), seed=7)
    turn = engine.apply(turn.state, "loot")
    restored = GameState.from_dict(turn.state.to_dict())
    assert restored.character.inventory == turn.state.character.inventory
    assert restored.flags == turn.state.flags
    assert {o.id for o in engine.available_options(restored)} == option_ids(turn)
