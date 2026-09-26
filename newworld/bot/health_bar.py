"""Картинка полосы здоровья.

Панель нарезана на состояния: файл `health-0.png` — все ячейки погасли,
`health-9.png` — все горят. Доля здоровья переводится в номер файла, а
его Telegram-идентификатор запоминается после первой отправки: одна и та
же картинка уходит игрокам десятки раз, и загружать её каждый раз
незачем.

Картинок может не быть вовсе — тогда бот показывает текстовую полосу и
работает как прежде.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Character

DEFAULT_DIR = Path("assets/health")
FILE_PATTERN = "health-{level}.png"


class HealthBarImages:
    """Набор картинок и запомненные идентификаторы уже отправленных."""

    def __init__(self, directory: str | Path = DEFAULT_DIR) -> None:
        self.directory = Path(directory)
        self._levels = self._scan()
        self._file_ids: dict[int, str] = {}

    def _scan(self) -> list[int]:
        """Какие уровни реально лежат на диске."""
        if not self.directory.is_dir():
            return []
        levels = []
        for level in range(100):
            if (self.directory / FILE_PATTERN.format(level=level)).is_file():
                levels.append(level)
        return levels

    @property
    def available(self) -> bool:
        """Есть ли хотя бы два уровня — иначе полоса ничего не показывает."""
        return len(self._levels) >= 2

    @property
    def steps(self) -> int:
        """Сколько делений у полосы: уровень 0 — пустая."""
        return max(self._levels) if self._levels else 0

    def level_for(self, character: Character) -> int:
        """Номер картинки под текущее здоровье.

        Живой персонаж не показывается пустой полосой, а мёртвый —
        непустой: у игрока не должно быть сомнений, жив он или нет.
        """
        top = self.steps
        if character.max_hp <= 0 or character.hp <= 0:
            return 0
        share = character.hp / character.max_hp
        level = round(share * top)
        return max(1, min(top, level))

    def path_for(self, character: Character) -> Path | None:
        if not self.available:
            return None
        path = self.directory / FILE_PATTERN.format(level=self.level_for(character))
        return path if path.is_file() else None

    # --- кэш идентификаторов Telegram ---------------------------------

    def cached_id(self, character: Character) -> str | None:
        return self._file_ids.get(self.level_for(character))

    def remember(self, character: Character, file_id: str) -> None:
        self._file_ids[self.level_for(character)] = file_id
