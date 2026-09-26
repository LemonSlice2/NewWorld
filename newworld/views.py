"""Представление состояния — общее для терминала и Telegram.

Рассказчик размечает текст простым HTML (его понимает Telegram). Для
терминала разметка снимается, поэтому обе оболочки показывают одно и то же.
"""

from __future__ import annotations

import html
import re

from .core.content import Option
from .core.models import Ability, Character

_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def strip_html(text: str) -> str:
    """Убрать разметку — для терминала и для промпта нейросети."""
    return html.unescape(_TAG_RE.sub("", text))


def health_bar(character: Character, width: int = 10) -> str:
    if character.max_hp <= 0:
        return ""
    filled = round(width * character.hp / character.max_hp)
    return "▰" * filled + "▱" * (width - filled)


def render_status(character: Character) -> str:
    """Карточка персонажа: то, что игрок должен видеть постоянно."""
    lines = [f"<b>{html.escape(character.name)}</b>"]
    if character.origin:
        lines.append(f"<i>{html.escape(character.origin)}</i>")
    lines += [
        f"❤️ {character.hp}/{character.max_hp}  {health_bar(character)}",
        f"🪙 {character.gold}",
    ]
    abilities = "  ".join(
        f"{ability.label[:3]} {character.abilities[ability]}"
        f"({character.modifier_for(ability):+d})"
        for ability in Ability
    )
    lines.append(abilities)
    if character.inventory:
        items = ", ".join(html.escape(item) for item in character.inventory)
        lines.append(f"🎒 {items}")
    else:
        lines.append("🎒 пусто")
    return "\n".join(lines)


def render_options_plain(options: tuple[Option, ...]) -> str:
    """Нумерованный список действий — для терминала."""
    if not options:
        return "(действий нет)"
    return "\n".join(f"  {i}. {option.label}" for i, option in enumerate(options, 1))
