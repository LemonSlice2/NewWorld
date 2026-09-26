"""Поиск токена: окружение и файл .env."""

import pytest

from newworld.config import TOKEN_ENV, load_env_file, read_token


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "нет-такого") == {}


def test_reads_token_from_env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"{TOKEN_ENV}=123:ABC\n", encoding="utf-8")
    assert read_token(path) == "123:ABC"


def test_environment_wins_over_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(f"{TOKEN_ENV}=из-файла\n", encoding="utf-8")
    monkeypatch.setenv(TOKEN_ENV, "из-окружения")
    assert read_token(path) == "из-окружения"


def test_ignores_comments_blank_lines_and_quotes(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "\n# комментарий\n"
        "ПУСТАЯ_СТРОКА_БЕЗ_РАВНО\n"
        f'  {TOKEN_ENV} = "123:ABC"  \n'
        "ДРУГАЯ=переменная\n",
        encoding="utf-8",
    )
    values = load_env_file(path)
    assert values[TOKEN_ENV] == "123:ABC"
    assert values["ДРУГАЯ"] == "переменная"
    assert "ПУСТАЯ_СТРОКА_БЕЗ_РАВНО" not in values


def test_no_token_anywhere_returns_none(tmp_path):
    assert read_token(tmp_path / ".env") is None


def test_blank_environment_value_is_treated_as_absent(tmp_path, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "   ")
    assert read_token(tmp_path / ".env") is None
