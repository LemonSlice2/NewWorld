"""Интерфейс рассказчика.

Рассказчик получает уже случившиеся факты и излагает их словами. Он не
бросает кости, не меняет хиты и не решает, что произошло — иначе игра
начнёт зависеть от его фантазии.

Сюда же позже встанет нейросетевая реализация (GigaChat, локальная модель
и т.д.): достаточно унаследоваться и реализовать narrate().
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.engine import Turn
from ..core.gendered import inflect


class Narrator(ABC):
    """Превращает ход в текст для игрока."""

    @abstractmethod
    def narrate(self, turn: Turn) -> str:
        """Описать, что произошло за ход, и что игрок видит сейчас."""

    def describe_scene(self, turn: Turn) -> str:
        """Описать текущую сцену без событий — например, при возврате в игру."""
        return inflect(turn.scene.text, turn.state.character.gender)
