"""Проверки связки бота с игрой — прежде всего защиты от старых кнопок."""

import pytest

from newworld.bot.keyboards import action_keyboard, parse_action
from newworld.bot.service import GameService, StaleAction
from newworld.core.content import Story
from newworld.narrator import TemplateNarrator
from newworld.storage import SaveStore


@pytest.fixture
def game(tmp_path):
    story = Story.load("content/olhovets.yaml")
    return GameService.create(
        story_id="olhovets",
        story=story,
        narrator=TemplateNarrator(),
        store=SaveStore(tmp_path / "saves.db"),
    )


@pytest.mark.asyncio
async def test_new_run_is_saved_and_resumable(game):
    turn = await game.start_new(user_id=1, name="Коля")
    assert turn.scene.id == game.story.start_scene

    resumed = await game.resume(user_id=1)
    assert resumed is not None
    assert resumed.scene.id == turn.scene.id
    assert {o.id for o in resumed.options} == {o.id for o in turn.options}


@pytest.mark.asyncio
async def test_resume_returns_none_without_save(game):
    assert await game.resume(user_id=404) is None


@pytest.mark.asyncio
async def test_action_advances_the_run(game):
    turn = await game.start_new(user_id=2, name="Коля")
    before = turn.state.turn
    turn = await game.act(user_id=2, expected_turn=before, option_index=0)
    assert turn.state.turn == before + 1

    saved = await game.resume(user_id=2)
    assert saved.state.turn == turn.state.turn


@pytest.mark.asyncio
async def test_button_from_an_old_message_is_rejected(game):
    """Главная защита: кнопка, нарисованная на прошлом ходе, не срабатывает."""
    turn = await game.start_new(user_id=3, name="Коля")
    stale_turn_number = turn.state.turn
    await game.act(user_id=3, expected_turn=stale_turn_number, option_index=0)

    with pytest.raises(StaleAction, match="старого сообщения"):
        await game.act(user_id=3, expected_turn=stale_turn_number, option_index=0)


@pytest.mark.asyncio
async def test_out_of_range_option_is_rejected(game):
    turn = await game.start_new(user_id=4, name="Коля")
    with pytest.raises(StaleAction):
        await game.act(user_id=4, expected_turn=turn.state.turn, option_index=99)


@pytest.mark.asyncio
async def test_action_without_save_is_rejected(game):
    with pytest.raises(StaleAction, match="/new"):
        await game.act(user_id=500, expected_turn=0, option_index=0)


@pytest.mark.asyncio
async def test_runs_of_different_players_do_not_mix(game):
    await game.start_new(user_id=10, name="Первый")
    await game.start_new(user_id=11, name="Второй")
    await game.act(user_id=10, expected_turn=0, option_index=0)

    first = await game.resume(user_id=10)
    second = await game.resume(user_id=11)
    assert first.state.turn == 1
    assert second.state.turn == 0
    assert second.state.character.name == "Второй"


@pytest.mark.asyncio
async def test_abandon_removes_the_save(game):
    await game.start_new(user_id=12, name="Коля")
    await game.abandon(user_id=12)
    assert await game.resume(user_id=12) is None


@pytest.mark.asyncio
async def test_callback_data_fits_telegram_limit(game):
    """Telegram отводит под callback_data 64 байта — проверяем с запасом."""
    turn = await game.start_new(user_id=13, name="Коля")
    keyboard = action_keyboard(turn.state.turn, turn.options)
    for row in keyboard.inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode("utf-8")) <= 64
            assert parse_action(button.callback_data) is not None


def test_parse_action_rejects_foreign_data():
    assert parse_action("мусор") is None
    assert parse_action("a:1") is None
    assert parse_action("a:x:y") is None
    assert parse_action("b:1:2") is None
