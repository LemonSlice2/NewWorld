"""Оформление окна.

Qt стилизуется таблицей, похожей на CSS. Всё оформление собрано здесь,
чтобы менять вид игры, не трогая её устройство.
"""

BACKGROUND = "#14120f"
PANEL = "#1c1916"
BORDER = "#3a332b"
TEXT = "#d8cfc0"
DIM = "#8a7f70"
ACCENT = "#c05a2a"

STYLE = f"""
QWidget {{
    background: {BACKGROUND};
    color: {TEXT};
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 15px;
}}

QTextBrowser, QScrollArea {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 14px;
}}

/* Кнопки действий: широкие, в столбец, с подсветкой под курсором. */
QPushButton {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 11px 16px;
    text-align: left;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: #ffffff;
}}
QPushButton:pressed {{
    background: #241f1a;
}}
QPushButton:disabled {{
    color: {DIM};
    border-color: #2a251f;
}}

QLabel#title {{
    font-size: 21px;
    color: #e8dfd0;
}}
QLabel#dim {{
    color: {DIM};
    font-size: 13px;
}}
QLabel#origin {{
    color: {DIM};
    font-style: italic;
}}

QLineEdit {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 9px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}

QScrollBar:vertical {{
    background: {BACKGROUND};
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
"""
