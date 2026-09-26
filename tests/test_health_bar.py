"""Полоса здоровья картинкой.

Главное требование — не сломать бота: картинок может не быть, их может
быть неполный набор, и в обоих случаях игра должна работать.
"""

import pytest

from newworld.bot.health_bar import HealthBarImages
from newworld.core.models import Character
from newworld.views import render_status


@pytest.fixture
def bars(tmp_path):
    for level in range(10):  # health-0 … health-9
        (tmp_path / f"health-{level}.png").write_bytes(b"fake png")
    return HealthBarImages(tmp_path)


def hero(hp, max_hp=10):
    return Character(name="Т", hp=hp, max_hp=max_hp)


def test_missing_directory_is_not_an_error(tmp_path):
    bars = HealthBarImages(tmp_path / "нет-такой-папки")
    assert not bars.available
    assert bars.path_for(hero(5)) is None


def test_single_image_is_not_enough_for_a_bar(tmp_path):
    (tmp_path / "health-0.png").write_bytes(b"fake")
    assert not HealthBarImages(tmp_path).available


def test_full_set_is_detected(bars):
    assert bars.available
    assert bars.steps == 9


def test_full_health_lights_every_cell(bars):
    assert bars.level_for(hero(10, 10)) == 9


def test_death_empties_the_bar(bars):
    assert bars.level_for(hero(0, 10)) == 0


def test_a_living_hero_never_shows_an_empty_bar(bars):
    """Один хит — это ещё жизнь, и полоса не должна врать, что её нет."""
    assert bars.level_for(hero(1, 100)) >= 1


def test_levels_do_not_exceed_available_images(bars):
    for max_hp in (1, 3, 7, 12, 40):
        for hp in range(max_hp + 1):
            level = bars.level_for(hero(hp, max_hp))
            assert 0 <= level <= bars.steps


def test_level_grows_with_health(bars):
    levels = [bars.level_for(hero(hp, 20)) for hp in range(21)]
    assert levels == sorted(levels)
    assert levels[0] == 0 and levels[-1] == 9


def test_broken_max_hp_does_not_crash(bars):
    assert bars.level_for(hero(5, 0)) == 0


def test_partial_set_still_works(tmp_path):
    """Нарезано только полдюжины уровней — бот всё равно должен работать."""
    for level in (0, 1, 2, 3):
        (tmp_path / f"health-{level}.png").write_bytes(b"fake")
    bars = HealthBarImages(tmp_path)
    assert bars.available and bars.steps == 3
    assert bars.path_for(hero(10, 10)).name == "health-3.png"


def test_file_id_is_remembered_per_level(bars):
    character = hero(10, 10)
    assert bars.cached_id(character) is None
    bars.remember(character, "telegram-id-9")
    assert bars.cached_id(character) == "telegram-id-9"
    # другой уровень — своя картинка, чужой идентификатор не подходит
    assert bars.cached_id(hero(3, 10)) is None


def test_same_level_reuses_the_same_id(bars):
    bars.remember(hero(10, 10), "id-full")
    assert bars.cached_id(hero(20, 20)) == "id-full"


# --- карточка персонажа ----------------------------------------------


def test_status_drops_text_bar_when_a_picture_shows_it():
    character = Character(name="Марфа", origin="Знахарка", hp=7, max_hp=12)
    with_bar = render_status(character, with_bar=True)
    without = render_status(character, with_bar=False)
    assert "▰" in with_bar and "▰" not in without
    assert "7/12" in without


def test_status_fits_telegram_caption_limit():
    """Карточка идёт подписью к фото, а подпись ограничена 1024 символами."""
    character = Character(
        name="Марфа Игнатьевна Пребольшая",
        origin="Уполномоченная · Хозяйственница",
        hp=7,
        max_hp=12,
        inventory=["Мандат уика", "Наган", "Счёты", "Пачка накладных", "Папиросы"] * 3,
    )
    assert len(render_status(character, with_bar=False)) < 1024
