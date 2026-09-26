"""Проверка окна игры.

Qt запускается без экрана (offscreen), поэтому весь путь игрока — от
выбора пола до хода в сцене — проверяется так же, как у бота. Окно ничего
не решает само, и здесь это видно: оно показывает то, что вернул движок.
"""

import os

import pytest

pytest.importorskip("PySide6", reason="десктопная оболочка не установлена")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from newworld.core.models import Gender  # noqa: E402
from newworld.desktop.window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qt_app, tmp_path):
    return MainWindow("content/olhovets.yaml", "assets/health", tmp_path / "save.db")


def button_labels(column) -> list[str]:
    layout = column._layout
    return [
        layout.itemAt(i).widget().text()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QPushButton)
    ]


def create_hero(window, class_index=0, subclass_index=0, gender=Gender.FEMALE, name="Марфа"):
    window._pick_gender(gender)
    character_class = window.story.classes[class_index]
    window._pick_class(character_class)
    subclasses = window.story.subclasses_of(character_class)
    if subclasses:
        window._pick_subclass(subclasses[subclass_index])
    window.name_screen.field.setText(name)
    window._finish_creation()


def test_opens_on_the_world_and_offers_a_gender(window):
    assert window.stack.currentWidget() is window.choice
    assert button_labels(window.choice.buttons) == ["Мужчина", "Женщина"]


def test_class_names_follow_the_chosen_gender(window):
    window._pick_gender(Gender.FEMALE)
    assert "Знахарка" in button_labels(window.choice.buttons)

    window._pick_gender(Gender.MALE)
    assert "Знахарь" in button_labels(window.choice.buttons)


def test_creation_leads_to_the_first_scene(window):
    create_hero(window)
    assert window.stack.currentWidget() is window.game
    assert window.turn.scene.id == window.story.start_scene
    assert window.game.sheet.name.text() == "Марфа"
    assert "Знахарка" in window.game.sheet.origin.text()


def test_scene_title_is_not_printed_twice(window):
    """Заголовок рисует окно, поэтому в тексте его быть не должно."""
    create_hero(window)
    body = window.game.scene.toPlainText()
    assert body.count(window.turn.scene.title.upper()) == 1
    assert window.turn.scene.title not in body.replace(window.turn.scene.title.upper(), "")


def test_buttons_match_available_options(window):
    create_hero(window)
    assert button_labels(window.game.buttons) == [o.label for o in window.turn.options]


def test_acting_advances_the_run_and_redraws_the_sheet(window):
    create_hero(window)
    before = window.turn.state.turn
    window._act(window.turn.options[-1].id)  # «Идти в деревню»
    assert window.turn.state.turn == before + 1
    assert button_labels(window.game.buttons) == [o.label for o in window.turn.options]


def test_subclass_opens_its_own_action(window):
    """Травница собирает травы, а книжница — нет: выбор виден в окне."""
    create_hero(window, class_index=0, subclass_index=0)
    травница = button_labels(window.game.buttons)
    window._restart()
    create_hero(window, class_index=0, subclass_index=3, name="Аглая")
    книжница = button_labels(window.game.buttons)
    assert травница != книжница


def test_run_survives_reopening_the_window(window, tmp_path):
    create_hero(window, name="Марфа")
    window._act(window.turn.options[-1].id)
    scene_id = window.turn.state.scene_id

    reopened = MainWindow("content/olhovets.yaml", "assets/health", window.store.path)
    assert reopened.turn is not None
    assert reopened.turn.state.scene_id == scene_id
    assert reopened.turn.state.character.name == "Марфа"
    assert reopened.stack.currentWidget() is reopened.game


def test_health_picture_is_shown_when_images_exist(window):
    create_hero(window)
    assert window.game.sheet.health_picture.isVisible() or window.game.sheet.health_picture.pixmap()


def test_missing_images_fall_back_to_a_text_bar(qt_app, tmp_path):
    window = MainWindow("content/olhovets.yaml", tmp_path / "нет-картинок", tmp_path / "s.db")
    create_hero(window)
    assert "▰" in window.game.sheet.health_text.text()
