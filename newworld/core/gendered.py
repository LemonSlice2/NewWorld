"""Согласование текста по полу героя.

Русский язык не даёт писать нейтрально там, где есть прошедшее время или
определение: «ты вышел» и «ты вышла» — разные строки. Заставлять автора
писать два варианта каждой сцены нельзя, поэтому в тексте ставится
развилка прямо по месту:

    Ты выш{ел|ла} наверх на рассвете и не увер{ен|ена}, что всё кончилось.

Слева мужская форма, справа женская. Всё остальное остаётся общим, и
сцена не раздваивается.
"""

from __future__ import annotations

import re

from .models import Gender

_FORK = re.compile(r"\{([^{}|]*)\|([^{}|]*)\}")


def inflect(text: str, gender: Gender) -> str:
    """Выбрать форму по полу во всех развилках текста."""
    index = 1 if gender is Gender.MALE else 2
    return _FORK.sub(lambda match: match.group(index), text)


def both_forms(text: str) -> tuple[str, str]:
    """Обе формы сразу — для проверок и для показа автору."""
    return inflect(text, Gender.MALE), inflect(text, Gender.FEMALE)
