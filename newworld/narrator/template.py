"""Шаблонный рассказчик: текст берётся из сюжетного файла.

Не требует ни сети, ни токенов, ни ключей. На нём игра полностью
играбельна — можно писать сюжет, крутить баланс и давать людям играть.
Нейросетевой рассказчик встанет рядом как вторая реализация.
"""

from __future__ import annotations

from ..core.engine import Turn
from ..core.gendered import inflect
from ..core.events import (
    CheckRolled,
    DamageTaken,
    Died,
    Event,
    FlagSet,
    GoldChanged,
    Healed,
    ItemGained,
    ItemLost,
    SceneEntered,
)
from .base import Narrator


class TemplateNarrator(Narrator):
    """Складывает текст из авторских формулировок и сухих строк о событиях.

    ``show_rolls`` управляет тем, видит ли игрок сами кости. Открытые броски
    — сознательный выбор: игрок верит проверяемым числам больше, чем
    словам «тебе не повезло».
    """

    def __init__(self, show_rolls: bool = True, show_scene_title: bool = True) -> None:
        self.show_rolls = show_rolls
        # Оболочка может рисовать заголовок сцены сама — тогда второй
        # заголовок в тексте только мешает.
        self.show_scene_title = show_scene_title

    def narrate(self, turn: Turn) -> str:
        parts: list[str] = []
        gender = turn.state.character.gender

        for event in turn.events:
            if isinstance(event, CheckRolled) and self.show_rolls:
                parts.append(self._render_check(event))

        if turn.branch_text:
            parts.append(turn.branch_text)

        mechanics = [
            line
            for line in (self._render_event(e) for e in turn.events)
            if line is not None
        ]
        if mechanics:
            parts.append("\n".join(mechanics))

        entered = [e for e in turn.events if isinstance(e, SceneEntered)]
        if entered:
            scene = turn.scene
            heading = f"<b>{scene.title}</b>\n" if self.show_scene_title else ""
            parts.append(f"{heading}{scene.text}")

        return inflect("\n\n".join(p for p in parts if p).strip(), gender)

    # --- отдельные события --------------------------------------------

    def _render_check(self, event: CheckRolled) -> str:
        result = event.result
        dice = " + ".join(str(r) for r in result.roll.rolls)
        modifier = f" {result.roll.modifier:+d}" if result.roll.modifier else ""
        return (
            f"🎲 <b>{event.ability.label}</b>: [{dice}]{modifier} = {result.roll.total} "
            f"против {result.dc} — <b>{result.outcome.label}</b>"
        )

    def _render_event(self, event: Event) -> str | None:
        """Сухая строка о механическом последствии. None — не показывать."""
        if isinstance(event, DamageTaken):
            return f"💔 Получено урона: {event.amount}"
        if isinstance(event, Healed):
            return f"💚 Восстановлено: {event.amount}"
        if isinstance(event, ItemGained):
            return f"🎒 Получено: {event.item}"
        if isinstance(event, ItemLost):
            return f"🎒 Потеряно: {event.item}"
        if isinstance(event, GoldChanged):
            if event.amount > 0:
                return f"🪙 Получено монет: {event.amount}"
            return f"🪙 Потрачено монет: {abs(event.amount)}"
        if isinstance(event, Died):
            return "☠️ <b>Ты погиб.</b>"
        if isinstance(event, (SceneEntered, CheckRolled, FlagSet)):
            # Переход описывается отдельно, бросок — выше, флаги игроку не нужны.
            return None
        return None
