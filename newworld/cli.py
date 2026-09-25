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
from .core.creation import roll_character
from .core.engine import Engine, InvalidAction, Turn
from .narrator import TemplateNarrator
from .views import render_options_plain, render_status, strip_html

RULE = "─" * 60


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
    args = parser.parse_args(argv)

    try:
        story = Story.load(args.story)
    except ContentError as exc:
        print(f"Ошибка в сюжете: {exc}", file=sys.stderr)
        return 1

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    character = roll_character(args.name, random.Random(seed))
    engine = Engine(story)
    narrator = TemplateNarrator(show_rolls=not args.hide_rolls)

    turn = engine.start(character, seed=seed)
    print(f"Сид забега: {seed}  (повторить: --seed {seed})")
    show(turn, narrator)

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
