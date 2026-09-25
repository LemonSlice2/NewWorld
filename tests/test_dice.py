import random

import pytest

from newworld.core.dice import Outcome, check, parse_notation, roll


class FixedRandom(random.Random):
    """ГСЧ, выдающий заданную последовательность — для проверки краёв."""

    def __init__(self, values):
        super().__init__()
        self._values = list(values)

    def randint(self, a, b):
        return self._values.pop(0)


def test_parse_notation():
    assert parse_notation("1d20") == (1, 20, 0)
    assert parse_notation("2d6+3") == (2, 6, 3)
    assert parse_notation("d8-1") == (1, 8, -1)
    assert parse_notation("1к20") == (1, 20, 0)  # русская «к»


@pytest.mark.parametrize("bad", ["", "abc", "0d6", "1d1", "200d6"])
def test_parse_notation_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_notation(bad)


def test_roll_sums_dice_and_modifiers():
    result = roll("2d6+1", FixedRandom([4, 5]), bonus=2)
    assert result.rolls == (4, 5)
    assert result.natural == 9
    assert result.total == 12  # 9 + 1 из записи + 2 бонуса


def test_natural_twenty_always_crits_even_below_dc():
    result = check(dc=99, rng=FixedRandom([20]))
    assert result.outcome is Outcome.CRIT_SUCCESS
    assert result.is_success


def test_natural_one_always_fails_even_above_dc():
    result = check(dc=1, rng=FixedRandom([1]), bonus=100)
    assert result.outcome is Outcome.CRIT_FAIL
    assert not result.is_success


def test_success_boundary_is_inclusive():
    assert check(dc=15, rng=FixedRandom([12]), bonus=3).outcome is Outcome.SUCCESS
    assert check(dc=15, rng=FixedRandom([11]), bonus=3).outcome is Outcome.FAIL


def test_margin_reports_distance_from_dc():
    assert check(dc=10, rng=FixedRandom([15])).margin == 5
    assert check(dc=10, rng=FixedRandom([4])).margin == -6
