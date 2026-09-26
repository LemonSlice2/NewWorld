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
from .core.creation import build_character, roll_character, starting_flags
from .core.gendered import inflect
from .core.models import Gender
from .core.engine import Engine, InvalidAction, Turn
from .narrator import TemplateNarrator
from .views import render_options_plain, render_status, strip_html

RULE = "─" * 60


def pick(title: str, items: list, describe) -> object:
    """Спросить выбор из списка. Возвращает выбранный элемент."""
    print(f"\n{RULE}\n{title}\n{RULE}")
    for index, item in enumerate(items, 1):
        print(f"\n  {index}. {describe(item)}")
    while True:
        try:
            raw = input("\nВыбор (номер): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nДо встречи.") from None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("Не понял. Введи номер.")


def create_character(story, preset_class: str | None, preset_name: str | None):
    """Провести игрока по созданию героя: пол, класс, специализация, имя."""
    if not story.classes:
        return Gender.MALE, None, None, preset_name or "Путник"

    gender = pick("КТО ПОЙДЁТ В ОЛЬХОВЕЦ?", list(Gender), lambda g: g.label)

    if preset_class is not None:
        character_class = next((c for c in story.classes if c.id == preset_class), None)
        if character_class is None:
            known = ", ".join(c.id for c in story.classes)
            raise SystemExit(f"Нет класса {preset_class!r}. Доступны: {known}")
    else:
        character_class = pick(
            inflect("КЕМ ТЫ БЫЛ{|А} ДО ЭТОЙ ДОРОГИ?", gender),
            list(story.classes),
            lambda c: f"{c.name.for_gender(gender)} — {c.tagline}",
        )
        print(f"\n{strip_html(inflect(character_class.description, gender))}")

    subclass = None
    subclasses = story.subclasses_of(character_class)
    if subclasses:
        subclass = pick(
            inflect("ЧЕМ ТЫ ЗАНИМАЛ{СЯ|АСЬ} В ЭТОМ РЕМЕСЛЕ?", gender),
            list(subclasses),
            lambda s: f"{s.name.for_gender(gender)} — {s.tagline}",
        )
        print(f"\n{strip_html(inflect(subclass.description, gender))}")

    name = preset_name
    if name is None:
        try:
            prompt = inflect("\nКак {его|её} зовут? (пусто — по ремеслу): ", gender)
            name = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nДо встречи.") from None
    return gender, character_class, subclass, name


def show(turn: Turn, narrator: TemplateNarrator) -> None:
    text = strip_html(narrator.narrate(turn))
    print(f"\n{RULE}\n{text}\n")
    print(strip_html(render_status(turn.state.character)))
    print(RULE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Текстовая игра в терминале")
    parser.add_argument("story", help="путь к YAML-файлу сюжета")
    parser.add_argument("--seed", type=int, default=None, help="сид для воспроизводимого забега")
    parser.add_argument("--name", default=None, help="имя персонажа (без него — спросит)")
    parser.add_argument("--hide-rolls", action="store_true", help="не показывать броски костей")
    parser.add_argument("--hero", default=None, help="id класса (без него — спросит)")
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

    gender, character_class, subclass, name = create_character(story, args.hero, args.name)
    if character_class is not None:
        character = build_character(name or "", gender, character_class, subclass)
        flags = starting_flags(character_class, subclass)
        print(f"\n{RULE}\n{character.name.upper()} — {character.origin}\n{RULE}")
    else:
        character = roll_character(name or "Путник", random.Random(seed), gender)
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
