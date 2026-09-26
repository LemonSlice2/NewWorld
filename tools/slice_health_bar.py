#!/usr/bin/env python3
"""Нарезать лист с полосами здоровья на отдельные состояния.

Генератор выдаёт картинки листами: на каждом несколько полос, у которых
горит разное число ячеек. Скрипт находит полосы по разрывам фона,
раскладывает по числу горящих ячеек и сохраняет как health-<N>.png.

    python tools/slice_health_bar.py assets/raw/лист.png --out assets/health

Разложить наверняка автоматика не всегда может (полосы на листе идут не
по порядку), поэтому скрипт печатает, что он посчитал, и позволяет
перепроверить глазами: --dry-run показывает, ничего не сохраняя.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

FILE_PATTERN = "health-{level}.png"


def find_rows(image: Image.Image, tolerance: int = 18) -> list[tuple[int, int]]:
    """Найти горизонтальные полосы: строки, отличающиеся от фона листа."""
    grey = image.convert("L")
    width, height = grey.size
    background = grey.getpixel((2, 2))
    pixels = grey.load()

    def row_has_content(y: int) -> bool:
        step = max(1, width // 200)
        different = sum(
            1 for x in range(0, width, step) if abs(pixels[x, y] - background) > tolerance
        )
        return different > (width // step) * 0.2

    rows: list[tuple[int, int]] = []
    start = None
    for y in range(height):
        if row_has_content(y):
            if start is None:
                start = y
        elif start is not None:
            if y - start > height * 0.02:  # слишком тонкое — это шов, не полоса
                rows.append((start, y))
            start = None
    if start is not None:
        rows.append((start, height))
    return rows


def find_columns(image: Image.Image, tolerance: int = 18) -> list[tuple[int, int]]:
    """Найти вертикальные группы — на листе полосы могут идти в два столбца."""
    grey = image.convert("L")
    width, height = grey.size
    background = grey.getpixel((2, 2))
    pixels = grey.load()

    def column_has_content(x: int) -> bool:
        step = max(1, height // 200)
        different = sum(
            1 for y in range(0, height, step) if abs(pixels[x, y] - background) > tolerance
        )
        return different > (height // step) * 0.1

    columns: list[tuple[int, int]] = []
    start = None
    for x in range(width):
        if column_has_content(x):
            if start is None:
                start = x
        elif start is not None:
            if x - start > width * 0.05:
                columns.append((start, x))
            start = None
    if start is not None:
        columns.append((start, width))
    return columns


def count_lit_cells(strip: Image.Image, min_width_ratio: float = 0.02) -> int:
    """Сколько ячеек горит.

    Считается не по одной линии поперёк полосы — JPEG её размывает, и
    счёт сбивается, — а по профилю: для каждого столбца пикселей берётся
    доля «горящих» по всей высоте, и уже в этом профиле ищутся плато.
    Так отдельные артефакты и блики не превращаются в лишнюю ячейку.
    """
    rgb = strip.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()

    # Ячейка горит, если она заметно краснее своего окружения.
    def is_lit(x: int, y: int) -> bool:
        r, g, b = pixels[x, y]
        return r > 110 and r - g > 55 and r - b > 55

    top, bottom = int(height * 0.3), int(height * 0.7)
    step = max(1, (bottom - top) // 12)
    rows = range(top, bottom, step)
    profile = [
        sum(1 for y in rows if is_lit(x, y)) / len(list(rows)) for x in range(width)
    ]

    min_width = max(3, int(width * min_width_ratio))
    count = 0
    run = 0
    for value in profile + [0.0]:
        if value > 0.5:
            run += 1
        else:
            if run >= min_width:
                count += 1
            run = 0
    return count


def slice_sheet(path: Path) -> list[tuple[int, Image.Image]]:
    """Разобрать лист: вернуть пары «сколько горит, картинка полосы».

    Границы полос определяются по фону неточно — на пару пикселей
    гуляют, — поэтому итоговое окно берётся одинаковым для всего листа и
    ставится по центру каждой полосы. Иначе картинки состояний выходят
    разной высоты и в чате дёргаются при смене.
    """
    sheet = Image.open(path)
    boxes: list[tuple[int, int, int, int]] = []  # left, right, центр, высота
    for left, right in find_columns(sheet) or [(0, sheet.width)]:
        column = sheet.crop((left, 0, right, sheet.height))
        for top, bottom in find_rows(column):
            boxes.append((left, right, (top + bottom) // 2, bottom - top))
    if not boxes:
        return []

    heights = sorted(box[3] for box in boxes)
    window = heights[len(heights) // 2]  # медиана: случайные обрезки не тянут

    result: list[tuple[int, Image.Image]] = []
    for left, right, centre, _ in boxes:
        top = max(0, centre - window // 2)
        strip = sheet.crop((left, top, right, min(sheet.height, top + window)))
        result.append((count_lit_cells(strip), strip))
    return result


def lit_profile(strip: Image.Image) -> list[float]:
    """Для каждого столбца — доля «горящих» пикселей по высоте ячейки."""
    rgb = strip.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    top, bottom = int(height * 0.3), int(height * 0.7)
    rows = list(range(top, bottom, max(1, (bottom - top) // 12)))

    def is_lit(x: int, y: int) -> bool:
        r, g, b = pixels[x, y]
        return r > 110 and r - g > 55 and r - b > 55

    return [sum(1 for y in rows if is_lit(x, y)) / len(rows) for x in range(width)]


def cell_bounds(reference: Image.Image, min_width_ratio: float = 0.02) -> list[tuple[int, int]]:
    """Где на полосе какая ячейка.

    Сетка снимается с эталона — полосы, где горят все ячейки: там каждая
    видна как самостоятельное красное пятно. По той же сетке потом
    правятся остальные состояния, поэтому ячейки совпадают до пикселя.
    """
    profile = lit_profile(reference)
    min_width = max(3, int(len(profile) * min_width_ratio))
    bounds: list[tuple[int, int]] = []
    start = None
    for x, value in enumerate(profile + [0.0]):
        if value > 0.5:
            if start is None:
                start = x
        elif start is not None:
            if x - start >= min_width:
                bounds.append((start, x))
            start = None
    return bounds


def cell_rows(reference: Image.Image, bounds: list[tuple[int, int]]) -> tuple[int, int]:
    """Верх и низ ячейки: копировать нужно её, а не декор рамки вокруг."""
    left, right = bounds[0]
    rgb = reference.convert("RGB")
    pixels = rgb.load()
    middle = (left + right) // 2
    lit_rows = []
    for y in range(reference.height):
        r, g, b = pixels[middle, y]
        if r > 110 and r - g > 55 and r - b > 55:
            lit_rows.append(y)
    if not lit_rows:
        return 0, reference.height
    pad = 4  # немного рамки вокруг, чтобы стык не был виден
    return max(0, lit_rows[0] - pad), min(reference.height, lit_rows[-1] + pad + 1)


def synthesize_level(
    source: Image.Image,
    source_level: int,
    target_level: int,
    bounds: list[tuple[int, int]],
) -> Image.Image:
    """Собрать недостающее состояние из соседнего, переставив ячейки.

    Генератор выдаёт состояния не подряд — какого-нибудь уровня может не
    оказаться вовсе. Но ячейки на полосе одинаковые, поэтому нужную
    достаточно скопировать из этой же картинки: горящую — чтобы зажечь,
    погасшую — чтобы погасить. Шов при этом невозможен: пиксели берутся
    из того же изображения, с той же подсветкой и тем же фоном.
    """
    if len(bounds) < max(source_level, target_level):
        raise ValueError(
            f"нашлось {len(bounds)} ячеек — мало, чтобы собрать уровень {target_level}"
        )
    result = source.copy()
    top, bottom = cell_rows(source, bounds)
    if target_level > source_level:
        donor_index, lo, hi = 0, source_level, target_level  # горящая — чтобы зажечь
    else:
        donor_index, lo, hi = len(bounds) - 1, target_level, source_level  # погасшая — чтобы погасить
    left, right = bounds[donor_index]
    donor = source.crop((left, top, right, bottom))
    for index in range(lo, hi):
        cell_left, cell_right = bounds[index]
        patch = donor.resize((cell_right - cell_left, bottom - top))
        result.paste(patch, (cell_left, top))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Нарезка полосы здоровья из листов генератора",
        epilog="Пример: python tools/slice_health_bar.py assets/raw/*.jpg --fill",
    )
    parser.add_argument("sheets", nargs="+", help="исходные листы (png/jpg)")
    parser.add_argument("--out", default="assets/health", help="куда сохранять")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что найдено")
    parser.add_argument(
        "--fill",
        action="store_true",
        help="достроить недостающие состояния из соседних (генератор выдаёт их не подряд)",
    )
    args = parser.parse_args(argv)

    found: dict[int, Image.Image] = {}
    for sheet_path in args.sheets:
        path = Path(sheet_path)
        if not path.is_file():
            print(f"нет файла: {path}", file=sys.stderr)
            return 1
        strips = slice_sheet(path)
        print(f"{path.name}: полос найдено {len(strips)}")
        for lit, strip in strips:
            keep = lit not in found
            note = "" if keep else "  — уже есть, пропуск"
            print(f"   горит ячеек: {lit:2d}  ({strip.width}×{strip.height}){note}")
            if keep:
                found[lit] = strip

    if not found:
        print("полос не найдено — проверь, что на листах ровные ряды на однотонном фоне")
        return 1

    missing = [n for n in range(max(found) + 1) if n not in found]
    if missing and args.fill:
        reference = found[max(found)]
        bounds = cell_bounds(reference)
        if len(bounds) < max(found):
            print(
                f"сетку ячеек снять не удалось (нашлось {len(bounds)}) — "
                "достроить не могу, уровни {missing} нужно догенерировать",
                file=sys.stderr,
            )
        else:
            for level in missing:
                # Ближайший уровень, а при равном расстоянии — тот, где горит больше:
                # гасить ячейку безопаснее, чем зажигать.
                donor = min(found, key=lambda other: (abs(other - level), -other))
                found[level] = synthesize_level(found[donor], donor, level, bounds)
                print(f"уровень {level} собран из уровня {donor}")
            missing = []
    if missing:
        print(f"\nне хватает уровней: {missing} (--fill достроит их из соседних)")

    if args.dry_run:
        print("\n--dry-run: ничего не сохранено")
        return 0

    # Полосы из разных столбцов листа отличаются на пару пикселей: в чате
    # это заметно как подрагивание при смене картинки.
    width = min(strip.width for strip in found.values())
    height = min(strip.height for strip in found.values())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for level, strip in sorted(found.items()):
        target = out / FILE_PATTERN.format(level=level)
        strip.crop((0, 0, width, height)).save(target)
    print(f"\nсохранено уровней: {len(found)}, размер {width}×{height}, папка {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
