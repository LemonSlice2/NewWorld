"""Броски костей и проверки характеристик.

Весь случай в игре живёт здесь. Движок получает генератор случайных чисел
снаружи, поэтому любой забег воспроизводится по сиду — это нужно и для
тестов, и для разбора жалоб игроков («у меня выпало вот это»).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from enum import Enum

_DICE_RE = re.compile(r"^\s*(\d*)\s*[dд]\s*(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


class Outcome(str, Enum):
    """Исход проверки. Порядок — от худшего к лучшему."""

    CRIT_FAIL = "crit_fail"
    FAIL = "fail"
    SUCCESS = "success"
    CRIT_SUCCESS = "crit_success"

    @property
    def is_success(self) -> bool:
        return self in (Outcome.SUCCESS, Outcome.CRIT_SUCCESS)

    @property
    def label(self) -> str:
        return _OUTCOME_LABELS[self]


_OUTCOME_LABELS = {
    Outcome.CRIT_FAIL: "провал",
    Outcome.FAIL: "неудача",
    Outcome.SUCCESS: "успех",
    Outcome.CRIT_SUCCESS: "блестящий успех",
}


@dataclass(frozen=True)
class Roll:
    """Результат одного броска: что кидали, что выпало, что вышло в сумме."""

    notation: str
    rolls: tuple[int, ...]
    modifier: int

    @property
    def natural(self) -> int:
        """Сумма на костях без модификаторов."""
        return sum(self.rolls)

    @property
    def total(self) -> int:
        return self.natural + self.modifier

    def __str__(self) -> str:
        body = " + ".join(str(r) for r in self.rolls)
        if self.modifier:
            body += f" {self.modifier:+d}"
        return f"{self.notation}: [{body}] = {self.total}"


@dataclass(frozen=True)
class CheckResult:
    """Проверка против сложности (DC)."""

    roll: Roll
    dc: int
    outcome: Outcome

    @property
    def is_success(self) -> bool:
        return self.outcome.is_success

    @property
    def margin(self) -> int:
        """На сколько перебрали или недобрали сложность."""
        return self.roll.total - self.dc


def parse_notation(notation: str) -> tuple[int, int, int]:
    """Разобрать запись вида ``1d20+3``. Принимает и русскую «к»/«д»."""
    match = _DICE_RE.match(notation.replace("к", "d").replace("К", "d"))
    if not match:
        raise ValueError(f"Не могу разобрать бросок: {notation!r}")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(3).replace(" ", "")) if match.group(3) else 0
    if count < 1 or sides < 2:
        raise ValueError(f"Бессмысленный бросок: {notation!r}")
    if count > 100:
        raise ValueError(f"Слишком много костей: {notation!r}")
    return count, sides, modifier


def roll(notation: str, rng: random.Random, bonus: int = 0) -> Roll:
    """Кинуть кости. ``bonus`` складывается с модификатором из записи."""
    count, sides, modifier = parse_notation(notation)
    rolls = tuple(rng.randint(1, sides) for _ in range(count))
    return Roll(notation=notation, rolls=rolls, modifier=modifier + bonus)


def check(dc: int, rng: random.Random, bonus: int = 0, notation: str = "1d20") -> CheckResult:
    """Проверка против сложности.

    Натуральная 20 — всегда блестящий успех, натуральная 1 — всегда провал,
    независимо от модификаторов. Это классическое правило и оно же не даёт
    прокачанному персонажу стать неуязвимым к случайности.
    """
    result = roll(notation, rng, bonus)
    single_d20 = result.notation.strip().lower() in ("1d20", "d20") or (
        len(result.rolls) == 1 and parse_notation(result.notation)[1] == 20
    )
    if single_d20 and result.natural == 20:
        outcome = Outcome.CRIT_SUCCESS
    elif single_d20 and result.natural == 1:
        outcome = Outcome.CRIT_FAIL
    elif result.total >= dc:
        outcome = Outcome.SUCCESS
    else:
        outcome = Outcome.FAIL
    return CheckResult(roll=result, dc=dc, outcome=outcome)
