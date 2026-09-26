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


def count_lit_cells(strip: Image.Image, threshold: int = 90) -> int:
    """Сколько ячеек горит: считаем красные пятна вдоль полосы."""
    rgb = strip.convert("RGB")
    width, height = rgb.size
    middle = height // 2
    pixels = rgb.load()
    lit = 0
    inside = False
    for x in range(width):
        r, g, b = pixels[x, middle]
        is_lit = r > 120 and r - g > threshold and r - b > threshold
        if is_lit and not inside:
            lit += 1
            inside = True
        elif not is_lit:
            inside = False
    return lit


def slice_sheet(path: Path) -> list[tuple[int, Image.Image]]:
    """Разобрать лист: вернуть пары «сколько горит, картинка полосы»."""
    sheet = Image.open(path)
    result: list[tuple[int, Image.Image]] = []
    for left, right in find_columns(sheet) or [(0, sheet.width)]:
        column = sheet.crop((left, 0, right, sheet.height))
        for top, bottom in find_rows(column):
            strip = column.crop((0, top, column.width, bottom))
            result.append((count_lit_cells(strip), strip))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Нарезка полосы здоровья")
    parser.add_argument("sheets", nargs="+", help="исходные листы (png/jpg)")
    parser.add_argument("--out", default="assets/health", help="куда сохранять")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что найдено")
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
            size = f"{strip.width}×{strip.height}"
            keep = lit not in found
            print(f"   горит ячеек: {lit:2d}  ({size})" + ("" if keep else "  — уже есть, пропуск"))
            if keep:
                found[lit] = strip

    missing = [n for n in range(max(found) + 1) if n not in found] if found else []
    if missing:
        print(f"\nне хватает уровней: {missing} — их нужно донарезать вручную")

    if args.dry_run:
        print("\n--dry-run: ничего не сохранено")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for lit, strip in sorted(found.items()):
        target = out / f"health-{lit}.png"
        strip.save(target)
        print(f"сохранено: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
