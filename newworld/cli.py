"""Игра в терминале — без Telegram, без токенов, без сети.

Это основной инструмент разработки: сюжет пишется и проверяется здесь,
а бот подключается уже к отлаженной игре.

    python -m newworld.cli content/olhovets.yaml
    python -m newworld.cli content/olhovets.yaml --seed 42   # воспроизводимый забег
"""

from __future__ import annotations

import argparse
import random
import sys

from .core.content import ContentError, Story
from .core.content import Archetype
from .core.creation import character_from_archetype, roll_character
from .core.engine import Engine, InvalidAction, Turn
from .narrator import TemplateNarrator
from .views import render_options_plain, render_status, strip_html

RULE = "─" * 60


def choose_archetype(archetypes: tuple[Archetype, ...], preset: str | None) -> Archetype | None:
    """Спросить, кем играть. None — в сюжете нет готовых героев."""
    if not archetypes:
        return None
    if preset is not None:
        for archetype in archetypes:
            if archetype.id == preset:
                return archetype
        known = ", ".join(a.id for a in archetypes)
        raise SystemExit(f"Нет персонажа {preset!r}. Доступны: {known}")
    print(f"\n{RULE}\nКЕМ ИГРАЕШЬ?\n{RULE}")
    for index, archetype in enumerate(archetypes, 1):
        print(f"\n  {index}. {archetype.name} — {archetype.tagline}")
    while True:
        try:
            raw = input("\nВыбор (номер): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nДо встречи.") from None
        if raw.isdigit() and 1 <= int(raw) <= len(archetypes):
            return archetypes[int(raw) - 1]
        print("Не понял. Введи номер.")


def show(turn: Turn, narrator: TemplateNarrator) -> None:
    text = strip_html(narrator.narrate(turn))
    print(f"\n{RULE}\n{text}\n")
    print(strip_html(render_status(turn.state.character)))
    print(RULE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Текстовая игра в терминале")
    parser.add_argument("story", help="путь к YAML-файлу сюжета")
    parser.add_argument("--seed", type=int, default=None, help="сид для воспроизводимого забега")
    parser.add_argument("--name", default="Путник", help="имя персонажа")
    parser.add_argument("--hide-rolls", action="store_true", help="не показывать броски костей")
    parser.add_argument("--hero", default=None, help="id персонажа (без него — спросит)")
    args = parser.parse_args(argv)

    try:
        story = Story.load(args.story)
    except ContentError as exc:
        print(f"Ошибка в сюжете: {exc}", file=sys.stderr)
        return 1

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    engine = Engine(story)
    narrator = TemplateNarrator(show_rolls=not args.hide_rolls)

    if story.world_intro:
        title = story.world_title or "Мир"
        print(f"\n{RULE}\n{title.upper()}\n{RULE}\n")
        print(strip_html(story.world_intro))

    archetype = choose_archetype(story.archetypes, args.hero)
    if archetype is not None:
        character = character_from_archetype(archetype)
        flags = archetype.flags
        print(f"\n{RULE}\nТы — {archetype.name.upper()}\n{RULE}\n")
        print(strip_html(archetype.description))
    else:
        character = roll_character(args.name, random.Random(seed))
        flags = ()

    turn = engine.start(character, seed=seed, flags=flags)
    show(turn, narrator)
    print(f"(сид забега {seed} — повторить этот же расклад: --seed {seed})")

    while not turn.is_over:
        print(render_options_plain(turn.options))
        try:
            raw = input("\nВыбор (номер, q — выход): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи.")
            return 0
        if raw.lower() in ("q", "quit", "выход"):
            print("До встречи.")
            return 0
        if not raw.isdigit() or not (1 <= int(raw) <= len(turn.options)):
            print("Не понял. Введи номер варианта.")
            continue
        option = turn.options[int(raw) - 1]
        try:
            turn = engine.apply(turn.state, option.id)
        except InvalidAction as exc:
            print(f"Нельзя: {exc}")
            continue
        show(turn, narrator)

    if turn.state.is_over:
        print("Забег окончен: персонаж погиб.")
    else:
        print("Забег окончен.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
