"""Чтение настроек из окружения и файла .env.

Токен бота — секрет: он живёт в переменной окружения или в .env, который
никогда не попадает в репозиторий. В коде и в сюжетных файлах его быть не
должно.

Своя маленькая читалка .env вместо библиотеки — чтобы запуск не зависел
от лишней зависимости: файл простой, разбирать в нём нечего.
"""

from __future__ import annotations

import os
from pathlib import Path

TOKEN_ENV = "NEWWORLD_BOT_TOKEN"


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Прочитать .env. Отсутствие файла — не ошибка.

    Переменные, уже заданные в окружении, имеют приоритет: так временный
    запуск с другим токеном не требует править файл.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def read_token(env_path: str | Path = ".env") -> str | None:
    """Найти токен бота: сначала в окружении, затем в .env."""
    token = os.environ.get(TOKEN_ENV)
    if token:
        return token.strip() or None
    return load_env_file(env_path).get(TOKEN_ENV) or None
