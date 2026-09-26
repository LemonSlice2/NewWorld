"""Главное окно игры.

Слева — сцена и действия, справа — лист персонажа. Создание героя идёт
теми же шагами, что и в боте: пол, класс, специализация, имя.

Оболочка ничего не решает сама: она показывает то, что вернул движок, и
передаёт ему выбор игрока.
"""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..bot.health_bar import HealthBarImages
from ..core.content import Story
from ..core.creation import build_character, starting_flags
from ..core.engine import Engine, Turn
from ..core.gendered import inflect
from ..core.models import Gender
from ..narrator import TemplateNarrator
from ..storage import SaveStore
from .sheet import CharacterSheet
from .theme import DIM, STYLE

SINGLE_PLAYER = 1  # в десктопе игрок один, но хранилище общее с ботом


class ButtonColumn(QWidget):
    """Столбец кнопок, который целиком перерисовывается на каждом шаге."""

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def show_options(self, options: list[tuple[str, object]], handler) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for label, value in options:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, v=value: handler(v))
            self._layout.addWidget(button)


class ChoiceScreen(QWidget):
    """Шаг создания героя: заголовок, пояснение и кнопки выбора."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setWordWrap(True)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(False)

        self.buttons = ButtonColumn()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.buttons)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout.addWidget(self.title)
        layout.addWidget(self.text, 3)
        layout.addWidget(scroll, 2)

    def show_step(self, title: str, text: str, options, handler) -> None:
        self.title.setText(title)
        self.text.setHtml(text)
        self.buttons.show_options(options, handler)


class NameScreen(QWidget):
    """Ввод имени героя."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        self.title = QLabel()
        self.title.setObjectName("title")
        self.text = QTextBrowser()
        self.field = QLineEdit()
        self.field.setMaxLength(24)
        self.hint = QLabel("Оставь пустым — и герой будет зваться по ремеслу.")
        self.hint.setObjectName("dim")
        self.accept = QPushButton("В путь")

        layout.addWidget(self.title)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.field)
        layout.addWidget(self.hint)
        layout.addWidget(self.accept)

        self.field.returnPressed.connect(self.accept.click)


class GameScreen(QWidget):
    """Сцена, действия и лист персонажа."""

    def __init__(self, health_images: HealthBarImages) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(14)
        self.scene = QTextBrowser()
        self.buttons = ButtonColumn()
        actions = QScrollArea()
        actions.setWidgetResizable(True)
        actions.setWidget(self.buttons)
        actions.setFrameShape(QScrollArea.Shape.NoFrame)
        left.addWidget(self.scene, 3)
        left.addWidget(actions, 2)

        self.sheet = CharacterSheet(health_images)
        sheet_box = QScrollArea()
        sheet_box.setWidgetResizable(True)
        sheet_box.setWidget(self.sheet)
        sheet_box.setFixedWidth(330)

        layout.addLayout(left, 1)
        layout.addWidget(sheet_box)


class MainWindow(QMainWindow):
    def __init__(self, story_path: str | Path, assets: str | Path, db: str | Path) -> None:
        super().__init__()
        self.story = Story.load(story_path)
        self.story_id = Path(story_path).stem
        self.engine = Engine(self.story)
        # Заголовок сцены рисует само окно, рассказчику он не нужен.
        self.narrator = TemplateNarrator(show_rolls=True, show_scene_title=False)
        self.store = SaveStore(db)
        self.health_images = HealthBarImages(assets)

        self.setWindowTitle(self.story.world_title or "NewWorld")
        self.setStyleSheet(STYLE)
        self.resize(1080, 720)

        self.choice = ChoiceScreen()
        self.name_screen = NameScreen()
        self.game = GameScreen(self.health_images)
        self.stack = QStackedWidget()
        for widget in (self.choice, self.name_screen, self.game):
            self.stack.addWidget(widget)
        self.setCentralWidget(self.stack)

        self.name_screen.accept.clicked.connect(self._finish_creation)

        self.gender = Gender.MALE
        self.character_class = None
        self.subclass = None
        self.turn: Turn | None = None

        self._resume_or_create()

    # --- создание героя -----------------------------------------------

    def _resume_or_create(self) -> None:
        """Продолжить прошлый забег, если он подходит к текущему сюжету."""
        saved = self.store.load_sync(SINGLE_PLAYER)
        if saved is not None:
            story_id, state = saved
            if story_id == self.story_id and state.scene_id in self.story.scenes:
                scene = self.story.scene(state.scene_id)
                self.turn = Turn(
                    state=state,
                    scene=scene,
                    events=(),
                    options=self.engine.available_options(state),
                    branch_text="",
                )
                if self.turn.options:
                    self._show_turn(scene.text)
                    return
            self.store.delete_sync(SINGLE_PLAYER)
        self._ask_gender()

    def _ask_gender(self) -> None:
        self.choice.show_step(
            self.story.world_title or "Новый мир",
            self.story.world_intro + "<br><br><b>Кто пойдёт в Ольховец?</b>",
            [(gender.label, gender) for gender in Gender],
            self._pick_gender,
        )
        self.stack.setCurrentWidget(self.choice)

    def _pick_gender(self, gender: Gender) -> None:
        self.gender = gender
        self._ask_class()

    def _ask_class(self) -> None:
        lines = [
            f"<b>{c.name.for_gender(self.gender)}</b> — {c.tagline}"
            for c in self.story.classes
        ]
        self.choice.show_step(
            inflect("Кем ты был{|а} до этой дороги?", self.gender),
            "<br><br>".join(lines),
            [(c.name.for_gender(self.gender), c) for c in self.story.classes],
            self._pick_class,
        )
        self.stack.setCurrentWidget(self.choice)

    def _pick_class(self, character_class) -> None:
        self.character_class = character_class
        subclasses = self.story.subclasses_of(character_class)
        if not subclasses:
            self._ask_name()
            return
        lines = [
            f"<b>{s.name.for_gender(self.gender)}</b> — {s.tagline}" for s in subclasses
        ]
        self.choice.show_step(
            inflect("Чем ты занимал{ся|ась} в этом ремесле?", self.gender),
            inflect(character_class.description, self.gender)
            + "<br><br>"
            + "<br><br>".join(lines),
            [(s.name.for_gender(self.gender), s) for s in subclasses]
            + [("← Другой путь", None)],
            self._pick_subclass,
        )
        self.stack.setCurrentWidget(self.choice)

    def _pick_subclass(self, subclass) -> None:
        if subclass is None:
            self._ask_class()
            return
        self.subclass = subclass
        self._ask_name()

    def _ask_name(self) -> None:
        subclass = self.subclass
        title = (
            subclass.name.for_gender(self.gender)
            if subclass
            else self.character_class.name.for_gender(self.gender)
        )
        description = subclass.description if subclass else self.character_class.description
        self.name_screen.title.setText(title)
        self.name_screen.text.setHtml(inflect(description, self.gender))
        self.name_screen.field.setPlaceholderText(
            inflect("Как {его|её} зовут?", self.gender)
        )
        self.name_screen.field.clear()
        self.stack.setCurrentWidget(self.name_screen)
        self.name_screen.field.setFocus()

    def _finish_creation(self) -> None:
        name = " ".join(self.name_screen.field.text().split())
        character = build_character(name, self.gender, self.character_class, self.subclass)
        flags = starting_flags(self.character_class, self.subclass)
        self.turn = self.engine.start(character, flags=flags)
        self._save()
        self._show_turn()

    # --- игра ----------------------------------------------------------

    def _save(self) -> None:
        if self.turn is not None:
            self.store.save_sync(SINGLE_PLAYER, self.story_id, self.turn.state)

    def _show_turn(self, text: str | None = None) -> None:
        turn = self.turn
        assert turn is not None
        body = text if text is not None else self.narrator.narrate(turn)
        title = html.escape(turn.scene.title)
        self.game.scene.setHtml(
            f"<div style='color:{DIM};letter-spacing:1px'>{title.upper()}</div>"
            f"<br>{body}"
        )
        self.game.sheet.show_character(turn.state.character)

        if turn.options:
            self.game.buttons.show_options(
                [(option.label, option.id) for option in turn.options], self._act
            )
        else:
            ending = "Забег окончен." if not turn.state.is_over else "Ты погиб."
            self.game.buttons.show_options(
                [(f"{ending}  Начать заново", None)], lambda _: self._restart()
            )
        self.stack.setCurrentWidget(self.game)

    def _act(self, option_id: str) -> None:
        assert self.turn is not None
        self.turn = self.engine.apply(self.turn.state, option_id)
        self._save()
        self._show_turn()

    def _restart(self) -> None:
        self.store.delete_sync(SINGLE_PLAYER)
        self.subclass = None
        self.character_class = None
        self._ask_gender()
