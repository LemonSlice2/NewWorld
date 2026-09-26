"""Запуск игры на компьютере.

    python -m newworld.desktop content/olhovets.yaml
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ..core.content import ContentError
from .window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NewWorld на компьютере")
    parser.add_argument("story", nargs="?", default="content/olhovets.yaml", help="файл сюжета")
    parser.add_argument("--assets", default="assets/health", help="картинки полосы здоровья")
    parser.add_argument("--save", default="newworld-save.db", help="файл сохранения")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    try:
        window = MainWindow(args.story, args.assets, args.save)
    except ContentError as exc:
        # Игрок не должен видеть трассировку: ошибка в сюжете — это
        # сообщение автору, и оно должно быть читаемым.
        QMessageBox.critical(None, "Ошибка в сюжете", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
