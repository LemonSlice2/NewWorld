"""Лист персонажа сбоку от сцены.

Всё, что игрок должен видеть постоянно: кто он, сколько здоровья,
характеристики и что в котомке. Полоса здоровья берётся из набора
картинок, а если их нет — рисуется символами.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..bot.health_bar import HealthBarImages
from ..core.models import Ability, Character
from ..views import health_bar as text_bar
from .theme import DIM


class CharacterSheet(QWidget):
    def __init__(self, health_images: HealthBarImages) -> None:
        super().__init__()
        self.health_images = health_images
        self._pixmaps: dict[int, QPixmap] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.name = QLabel()
        self.name.setObjectName("title")
        self.name.setWordWrap(True)

        self.origin = QLabel()
        self.origin.setObjectName("origin")
        self.origin.setWordWrap(True)

        self.health_picture = QLabel()
        self.health_picture.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.health_text = QLabel()

        self.abilities = QLabel()
        self.abilities.setWordWrap(True)

        self.purse = QLabel()
        self.inventory = QLabel()
        self.inventory.setWordWrap(True)

        for widget in (
            self.name,
            self.origin,
            self.health_picture,
            self.health_text,
            self.abilities,
            self.purse,
            self.inventory,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)

    def _health_pixmap(self, character: Character) -> QPixmap | None:
        """Картинка полосы. Один раз прочитали с диска — дальше из памяти."""
        level = self.health_images.level_for(character)
        if level in self._pixmaps:
            return self._pixmaps[level]
        path = self.health_images.path_for(character)
        if path is None:
            return None
        pixmap = QPixmap(str(path)).scaledToWidth(
            280, Qt.TransformationMode.SmoothTransformation
        )
        self._pixmaps[level] = pixmap
        return pixmap

    def show_character(self, character: Character) -> None:
        self.name.setText(html.escape(character.name))
        self.origin.setText(html.escape(character.origin))

        pixmap = self._health_pixmap(character)
        if pixmap is not None:
            self.health_picture.setPixmap(pixmap)
            self.health_picture.show()
            self.health_text.setText(
                f"<span style='color:{DIM}'>Здоровье</span> "
                f"{character.hp} / {character.max_hp}"
            )
        else:
            self.health_picture.hide()
            self.health_text.setText(
                f"<span style='color:{DIM}'>Здоровье</span> "
                f"{character.hp} / {character.max_hp}  {text_bar(character)}"
            )

        rows = "".join(
            f"<tr><td style='color:{DIM};padding-right:14px'>{ability.label}</td>"
            f"<td align='right'>{character.abilities[ability]}</td>"
            f"<td align='right' style='padding-left:10px'>"
            f"{character.modifier_for(ability):+d}</td></tr>"
            for ability in Ability
        )
        self.abilities.setText(f"<table>{rows}</table>")

        self.purse.setText(
            f"<span style='color:{DIM}'>Монет</span> {character.gold}"
        )
        if character.inventory:
            items = "<br>".join("— " + html.escape(i) for i in character.inventory)
        else:
            items = f"<span style='color:{DIM}'>пусто</span>"
        self.inventory.setText(f"<span style='color:{DIM}'>Котомка</span><br>{items}")
