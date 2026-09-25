"""Запуск Telegram-бота.

    export NEWWORLD_BOT_TOKEN="токен от @BotFather"
    python -m newworld.bot content/olhovets.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ..core.content import ContentError, Story
from ..narrator import TemplateNarrator
from ..storage import SaveStore
from .app import build_router
from .service import GameService

TOKEN_ENV = "NEWWORLD_BOT_TOKEN"


async def run(story_path: str, db_path: str, token: str) -> None:
    story = Story.load(story_path)
    game = GameService.create(
        story_id=Path(story_path).stem,
        story=story,
        narrator=TemplateNarrator(show_rolls=True),
        store=SaveStore(db_path),
    )
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(game))
    logging.info("Сюжет загружен: %d сцен", len(story.scenes))
    await dispatcher.start_polling(bot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram-бот текстовой игры")
    parser.add_argument("story", help="путь к YAML-файлу сюжета")
    parser.add_argument("--db", default="saves.db", help="файл сохранений")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    token = os.environ.get(TOKEN_ENV)
    if not token:
        print(
            f"Не задан {TOKEN_ENV}. Получи токен у @BotFather и выполни:\n"
            f'  export {TOKEN_ENV}="сюда_токен"',
            file=sys.stderr,
        )
        return 2

    try:
        asyncio.run(run(args.story, args.db, token))
    except ContentError as exc:
        print(f"Ошибка в сюжете: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        logging.info("Остановлено")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
