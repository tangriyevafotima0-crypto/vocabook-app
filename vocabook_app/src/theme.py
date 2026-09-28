"""
theme.py — Shared macOS-style dark theme constants for Vocabook.

Palette per spec:
    Canvas / Deep Midnight Obsidian  #0C0E14
    Card Surface                      #151922
    Border                            #1F2633
    Soft Indigo (focus/selection)     #6366F1
    Sage Emerald (mastery/correct)    #10B981
    Coral/Crimson (warning/"Again")   #F43F5E
    Muted Gray (secondary text)       #94A3B8
"""

COLOR_BG = "#0C0E14"
COLOR_SURFACE = "#151922"
COLOR_SURFACE_ALT = "#1A1F2B"
COLOR_BORDER = "#1F2633"
COLOR_INDIGO = "#6366F1"
COLOR_INDIGO_DIM = "#4548B0"
COLOR_EMERALD = "#10B981"
COLOR_CRIMSON = "#F43F5E"
COLOR_MUTED = "#94A3B8"
COLOR_TEXT = "#E7EBF3"
COLOR_AMBER = "#F59E0B"

FONT_FAMILY = "-apple-system, 'SF Pro Display', 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"

APP_STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
}}

QMainWindow {{
    background-color: {COLOR_BG};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_INDIGO_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QPushButton {{
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    background: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT};
}}
QPushButton:hover {{
    background: {COLOR_BORDER};
}}
QPushButton:pressed {{
    background: {COLOR_BG};
}}
QPushButton:disabled {{
    color: {COLOR_MUTED};
    background: {COLOR_SURFACE};
}}

QPushButton#PrimaryButton {{
    background: {COLOR_INDIGO};
    color: white;
}}
QPushButton#PrimaryButton:hover {{
    background: {COLOR_INDIGO_DIM};
}}

QPushButton#AgainButton {{
    background: rgba(244, 63, 94, 0.16);
    color: {COLOR_CRIMSON};
    border: 1px solid rgba(244, 63, 94, 0.4);
}}
QPushButton#AgainButton:hover {{ background: rgba(244, 63, 94, 0.28); }}

QPushButton#HardButton {{
    background: rgba(245, 158, 11, 0.14);
    color: {COLOR_AMBER};
    border: 1px solid rgba(245, 158, 11, 0.35);
}}
QPushButton#HardButton:hover {{ background: rgba(245, 158, 11, 0.24); }}

QPushButton#GoodButton {{
    background: rgba(99, 102, 241, 0.16);
    color: {COLOR_INDIGO};
    border: 1px solid rgba(99, 102, 241, 0.4);
}}
QPushButton#GoodButton:hover {{ background: rgba(99, 102, 241, 0.28); }}

QPushButton#EasyButton {{
    background: rgba(16, 185, 129, 0.16);
    color: {COLOR_EMERALD};
    border: 1px solid rgba(16, 185, 129, 0.4);
}}
QPushButton#EasyButton:hover {{ background: rgba(16, 185, 129, 0.28); }}

QLabel#MutedLabel {{
    color: {COLOR_MUTED};
}}

QFrame#Card {{
    background: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 16px;
}}

QFrame#SetCard {{
    background: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 14px;
}}
QFrame#SetCard:hover {{
    border: 1px solid {COLOR_INDIGO};
}}

QProgressBar {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {COLOR_EMERALD};
    border-radius: 5px;
}}

QLineEdit {{
    background: {COLOR_SURFACE_ALT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    color: {COLOR_TEXT};
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid {COLOR_INDIGO};
}}

QListWidget {{
    background: transparent;
    border: none;
}}

QSplitter::handle {{
    background: {COLOR_BORDER};
}}

QToolTip {{
    background: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px 8px;
    border-radius: 6px;
}}
"""
