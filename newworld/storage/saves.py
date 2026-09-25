"""Сохранения забегов в SQLite.

Состояние хранится одним JSON-документом: его формат задаёт GameState, и
пока сюжет не требует запросов «найди всех, у кого есть фонарь», отдельные
колонки под каждое поле только мешали бы менять модель.

SQLite синхронный, поэтому публичные методы — асинхронные обёртки: под
asyncio нельзя блокировать цикл событий обращением к диску.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from ..core.models import GameState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    user_id    INTEGER PRIMARY KEY,
    story_id   TEXT    NOT NULL,
    state      TEXT    NOT NULL,
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


class SaveStore:
    """Одно активное сохранение на игрока."""

    def __init__(self, path: str | Path = "saves.db") -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    # --- синхронное ядро ----------------------------------------------

    def _load(self, user_id: int) -> tuple[str, GameState] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT story_id, state FROM saves WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        story_id, payload = row
        return story_id, GameState.from_dict(json.loads(payload))

    def _save(self, user_id: int, story_id: str, state: GameState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO saves (user_id, story_id, state, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    story_id   = excluded.story_id,
                    state      = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (user_id, story_id, payload),
            )

    def _delete(self, user_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM saves WHERE user_id = ?", (user_id,))

    # --- асинхронный интерфейс ----------------------------------------

    async def load(self, user_id: int) -> tuple[str, GameState] | None:
        return await asyncio.to_thread(self._load, user_id)

    async def save(self, user_id: int, story_id: str, state: GameState) -> None:
        await asyncio.to_thread(self._save, user_id, story_id, state)

    async def delete(self, user_id: int) -> None:
        await asyncio.to_thread(self._delete, user_id)
