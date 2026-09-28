"""
app.py — Vocabook main application.

Wires together:
    - Database (database.py)     persistence
    - SRS engine (srs_engine.py) scheduling logic
    - HUD widget (hud.py)        ambient anti-distraction overlay
    - Theme (theme.py)           shared macOS-dark styling

Screens:
    1. Table of Contents  — books -> sets, with mastery % and due counts.
    2. Drill session       — flip-card flow with Again/Hard/Good/Easy.
    3. Session summary      — quick recap after finishing a drill.
"""

from __future__ import annotations

import sys
import os
import datetime

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QTimer, QSize,
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QGridLayout, QGraphicsOpacityEffect,
    QStackedWidget, QSizePolicy, QSpacerItem, QMessageBox,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import Database, DEFAULT_DB_PATH
from srs_engine import schedule, state_from_row, Rating
from hud import HUDWidget
from theme import (
    APP_STYLESHEET, COLOR_BG, COLOR_SURFACE, COLOR_SURFACE_ALT, COLOR_BORDER,
    COLOR_INDIGO, COLOR_EMERALD, COLOR_CRIMSON, COLOR_MUTED, COLOR_TEXT,
    COLOR_AMBER,
)


APP_TITLE = "Vocabook"
WINDOW_MIN_SIZE = (980, 680)


# ---------------------------------------------------------------------- #
# Table of Contents
# ---------------------------------------------------------------------- #

class SetCard(QFrame):
    """One clickable tile representing a single vocabulary set."""

    clicked = pyqtSignal(int)  # set_id

    def __init__(self, set_row, mastery: float, due_count: int, parent=None):
        super().__init__(parent)
        self.set_id = set_row["id"]
        self.setObjectName("SetCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        title = QLabel(set_row["title"])
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLOR_TEXT};")
        top_row.addWidget(title)
        top_row.addStretch(1)

        if due_count > 0:
            due_badge = QLabel(f"{due_count} due")
            due_badge.setStyleSheet(f"""
                background: rgba(244, 63, 94, 0.16);
                color: {COLOR_CRIMSON};
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            """)
            top_row.addWidget(due_badge)
        layout.addLayout(top_row)

        count_label = QLabel(f"{set_row['total_words']} words")
        count_label.setObjectName("MutedLabel")
        count_label.setStyleSheet(f"font-size: 12px; color: {COLOR_MUTED};")
        layout.addWidget(count_label)

        layout.addStretch(1)

        # mastery bar
        bar_bg = QFrame()
        bar_bg.setFixedHeight(6)
        bar_bg.setStyleSheet(f"background: {COLOR_BORDER}; border-radius: 3px;")
        bar_layout = QHBoxLayout(bar_bg)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_fill = QFrame()
        bar_fill.setStyleSheet(
            f"background: {COLOR_EMERALD}; border-radius: 3px;"
        )
        bar_layout.addWidget(bar_fill, int(max(1, mastery)))
        if mastery < 100:
            bar_layout.addSpacerItem(
                QSpacerItem(1, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            )
            bar_layout.setStretch(1, int(max(1, 100 - mastery)))
        layout.addWidget(bar_bg)

        mastery_label = QLabel(f"{mastery:.0f}% mastered")
        mastery_label.setStyleSheet(f"font-size: 11px; color: {COLOR_MUTED};")
        layout.addWidget(mastery_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.set_id)
        super().mousePressEvent(event)


class TOCScreen(QWidget):
    """Visual Table of Contents: books grouped, sets as tiles."""

    set_selected = pyqtSignal(int)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(4)

        header_row = QHBoxLayout()
        header = QLabel("Vocabook")
        header.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {COLOR_TEXT};")
        header_row.addWidget(header)
        header_row.addStretch(1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(f"font-size: 13px; color: {COLOR_MUTED};")
        header_row.addWidget(self.stats_label)
        outer.addLayout(header_row)

        subtitle = QLabel("Choose a set to review, or launch a targeted drill.")
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLOR_MUTED}; margin-bottom: 8px;")
        outer.addWidget(subtitle)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 8, 8, 24)
        self.content_layout.setSpacing(22)
        self.scroll.setWidget(self.content)

        self.reload()

    def reload(self):
        # clear
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        total_cards = self.db.total_card_count()
        total_due = self.db.global_due_count()
        self.stats_label.setText(f"{total_cards} words  ·  {total_due} due today")

        books = self.db.list_books()
        if not books:
            empty = QLabel(
                "No vocabulary loaded yet.\nRun run.sh to ingest your book into the database."
            )
            empty.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 14px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(empty)
            return

        for book in books:
            book_label = QLabel(book["title"])
            book_label.setStyleSheet(
                f"font-size: 17px; font-weight: 700; color: {COLOR_TEXT}; "
                f"padding-bottom: 2px; border-bottom: 1px solid {COLOR_BORDER};"
            )
            self.content_layout.addWidget(book_label)

            grid = QGridLayout()
            grid.setSpacing(14)
            sets = self.db.list_sets_for_book(book["id"])
            cols = 4
            for idx, s in enumerate(sets):
                mastery = self.db.set_mastery(s["id"])
                due = self.db.set_due_count(s["id"])
                card = SetCard(s, mastery, due)
                card.clicked.connect(self.set_selected.emit)
                grid.addWidget(card, idx // cols, idx % cols)
            grid_widget = QWidget()
            grid_widget.setLayout(grid)
            self.content_layout.addWidget(grid_widget)


# ---------------------------------------------------------------------- #
# Flashcard / Drill screen
# ---------------------------------------------------------------------- #

class FlipCard(QFrame):
    """A single flashcard surface with a cross-fade flip between the word
    (front) and its definition/example/antonym (back)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(320)

        self._showing_back = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(16)
        layout.addStretch(1)

        self.word_label = QLabel("")
        self.word_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.word_label.setWordWrap(True)
        self.word_label.setStyleSheet(
            f"font-size: 36px; font-weight: 800; color: {COLOR_TEXT};"
        )
        layout.addWidget(self.word_label)

        self.hint_label = QLabel("Click Reveal to see the definition")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet(f"font-size: 12px; color: {COLOR_MUTED};")
        layout.addWidget(self.hint_label)

        # back content, hidden until revealed
        self.back_container = QWidget()
        back_layout = QVBoxLayout(self.back_container)
        back_layout.setContentsMargins(0, 8, 0, 0)
        back_layout.setSpacing(14)

        self.definition_label = QLabel("")
        self.definition_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.definition_label.setWordWrap(True)
        self.definition_label.setStyleSheet(
            f"font-size: 17px; color: {COLOR_TEXT}; font-weight: 500;"
        )
        back_layout.addWidget(self.definition_label)

        self.example_label = QLabel("")
        self.example_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.example_label.setWordWrap(True)
        self.example_label.setStyleSheet(
            f"font-size: 13px; color: {COLOR_MUTED}; font-style: italic;"
        )
        back_layout.addWidget(self.example_label)

        self.antonym_label = QLabel("")
        self.antonym_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.antonym_label.setStyleSheet(
            f"font-size: 12px; color: {COLOR_CRIMSON}; font-weight: 600;"
        )
        back_layout.addWidget(self.antonym_label)

        self.back_container.setVisible(False)
        layout.addWidget(self.back_container)

        layout.addStretch(1)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(1.0)
        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(180)

    def load_card(self, row):
        self._showing_back = False
        self.word_label.setText(row["word"])
        self.hint_label.setText("Click Reveal to see the definition")
        self.hint_label.setVisible(True)
        self.back_container.setVisible(False)

        self.definition_label.setText(row["definition"])
        self.example_label.setText(f"“{row['example']}”" if row["example"] else "")
        self.example_label.setVisible(bool(row["example"]))
        self.antonym_label.setText(
            f"Antonym: {row['antonym']}" if row["antonym"] else ""
        )
        self.antonym_label.setVisible(bool(row["antonym"]))

        self._opacity_effect.setOpacity(1.0)
        self._fade_in()

    def _fade_in(self):
        self._disconnect_anim_finished()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _disconnect_anim_finished(self):
        try:
            self._anim.finished.disconnect()
        except TypeError:
            pass  # nothing was connected — fine

    def reveal(self):
        if self._showing_back:
            return
        self._showing_back = True

        self._disconnect_anim_finished()
        self._anim.stop()
        self._anim.setDuration(140)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def _swap():
            self._disconnect_anim_finished()
            self.hint_label.setVisible(False)
            self.back_container.setVisible(True)
            fade_back = QPropertyAnimation(self._opacity_effect, b"opacity")
            fade_back.setDuration(180)
            fade_back.setStartValue(0.0)
            fade_back.setEndValue(1.0)
            fade_back.setEasingCurve(QEasingCurve.Type.OutCubic)
            fade_back.start()
            self._anim2 = fade_back  # keep alive until it finishes

        self._anim.finished.connect(_swap)
        self._anim.start()

    @property
    def showing_back(self):
        return self._showing_back


class DrillScreen(QWidget):
    """Runs a spaced-repetition review session for one set's due cards."""

    finished = pyqtSignal(int, int)  # (reviewed_count, correct_count)
    exited = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.queue: list = []
        self.index = 0
        self.reviewed = 0
        self.correct = 0
        self.set_title = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 28)
        outer.setSpacing(18)

        top_row = QHBoxLayout()
        back_btn = QPushButton("← Back to sets")
        back_btn.clicked.connect(self._exit)
        top_row.addWidget(back_btn)
        top_row.addStretch(1)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 13px;")
        top_row.addWidget(self.progress_label)
        outer.addLayout(top_row)

        self.set_title_label = QLabel("")
        self.set_title_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {COLOR_TEXT};"
        )
        outer.addWidget(self.set_title_label)

        outer.addStretch(1)

        self.card = FlipCard()
        outer.addWidget(self.card)

        outer.addStretch(1)

        # controls stack: Reveal button, then 4-way rating row
        self.controls_stack = QStackedWidget()
        self.controls_stack.setFixedHeight(64)

        reveal_page = QWidget()
        reveal_layout = QHBoxLayout(reveal_page)
        reveal_layout.setContentsMargins(0, 0, 0, 0)
        reveal_layout.addStretch(1)
        self.reveal_btn = QPushButton("Reveal")
        self.reveal_btn.setObjectName("PrimaryButton")
        self.reveal_btn.setMinimumWidth(180)
        self.reveal_btn.setMinimumHeight(46)
        self.reveal_btn.clicked.connect(self._on_reveal)
        reveal_layout.addWidget(self.reveal_btn)
        reveal_layout.addStretch(1)
        self.controls_stack.addWidget(reveal_page)

        rating_page = QWidget()
        rating_layout = QHBoxLayout(rating_page)
        rating_layout.setContentsMargins(0, 0, 0, 0)
        rating_layout.setSpacing(12)

        self.again_btn = self._make_rating_btn("Again", "AgainButton", Rating.AGAIN)
        self.hard_btn = self._make_rating_btn("Hard", "HardButton", Rating.HARD)
        self.good_btn = self._make_rating_btn("Good", "GoodButton", Rating.GOOD)
        self.easy_btn = self._make_rating_btn("Easy", "EasyButton", Rating.EASY)
        for b in (self.again_btn, self.hard_btn, self.good_btn, self.easy_btn):
            rating_layout.addWidget(b)
        self.controls_stack.addWidget(rating_page)

        outer.addWidget(self.controls_stack)

    def _make_rating_btn(self, label, object_name, rating: Rating) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName(object_name)
        btn.setMinimumHeight(46)
        btn.clicked.connect(lambda: self._on_rate(rating))
        return btn

    # ------------------------------------------------------------------ #
    def start(self, set_id: int, set_title: str):
        self.set_title = set_title
        self.queue = list(self.db.get_due_cards_for_set(set_id))
        if not self.queue:
            # nothing due — allow a free-review pass over the whole set
            self.queue = list(self.db.get_cards_for_set(set_id))
        self.index = 0
        self.reviewed = 0
        self.correct = 0
        self.set_title_label.setText(set_title)
        self._show_current()

    def _show_current(self):
        if self.index >= len(self.queue):
            self.finished.emit(self.reviewed, self.correct)
            return
        row = self.queue[self.index]
        self.card.load_card(row)
        self.controls_stack.setCurrentIndex(0)
        self.progress_label.setText(f"{self.index + 1} / {len(self.queue)}")

    def _on_reveal(self):
        self.card.reveal()
        QTimer.singleShot(160, lambda: self.controls_stack.setCurrentIndex(1))

    def _on_rate(self, rating: Rating):
        row = self.queue[self.index]
        state = state_from_row(row)
        result = schedule(state, rating)

        self.db.update_card_srs(
            card_id=row["id"],
            interval=result.interval,
            ease_factor=result.ease_factor,
            repetitions=result.repetitions,
            box_level=result.box_level,
            due_date=result.due_date,
            correct=result.correct,
        )
        self.db.log_review(row["id"], rating.value)

        self.reviewed += 1
        if result.correct:
            self.correct += 1

        self.index += 1
        self._show_current()

    def _exit(self):
        self.exited.emit()


class SessionSummaryScreen(QWidget):
    """Brief recap shown after a drill session completes."""

    done = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self.icon_label = QLabel("✓")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(
            f"font-size: 48px; color: {COLOR_EMERALD}; font-weight: 800;"
        )
        layout.addWidget(self.icon_label)

        self.headline = QLabel("Session complete")
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {COLOR_TEXT};"
        )
        layout.addWidget(self.headline)

        self.detail = QLabel("")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setStyleSheet(f"font-size: 14px; color: {COLOR_MUTED};")
        layout.addWidget(self.detail)

        btn = QPushButton("Back to sets")
        btn.setObjectName("PrimaryButton")
        btn.setMinimumWidth(180)
        btn.setMinimumHeight(44)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        btn.clicked.connect(self.done.emit)

    def show_result(self, reviewed: int, correct: int):
        if reviewed == 0:
            self.detail.setText("No cards were due in this set.")
        else:
            pct = round(100 * correct / reviewed)
            self.detail.setText(
                f"Reviewed {reviewed} card{'s' if reviewed != 1 else ''} — "
                f"{correct} correct ({pct}%)."
            )


# ---------------------------------------------------------------------- #
# Main window
# ---------------------------------------------------------------------- #

class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle(APP_TITLE)
        self.resize(*WINDOW_MIN_SIZE)
        self.setMinimumSize(*WINDOW_MIN_SIZE)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.toc_screen = TOCScreen(db)
        self.drill_screen = DrillScreen(db)
        self.summary_screen = SessionSummaryScreen()

        self.stack.addWidget(self.toc_screen)     # index 0
        self.stack.addWidget(self.drill_screen)   # index 1
        self.stack.addWidget(self.summary_screen) # index 2

        self.toc_screen.set_selected.connect(self._launch_drill)
        self.drill_screen.finished.connect(self._on_drill_finished)
        self.drill_screen.exited.connect(self._show_toc)
        self.summary_screen.done.connect(self._show_toc)

        self._current_set_id = None

    def _launch_drill(self, set_id: int):
        # find set title
        row = None
        for s in self.db.list_all_sets_with_books():
            if s["id"] == set_id:
                row = s
                break
        title = f"{row['book_title']} — {row['title']}" if row else "Drill"
        self._current_set_id = set_id
        self.drill_screen.start(set_id, title)
        self.stack.setCurrentIndex(1)

    def _on_drill_finished(self, reviewed: int, correct: int):
        self.summary_screen.show_result(reviewed, correct)
        self.stack.setCurrentIndex(2)

    def _show_toc(self):
        self.toc_screen.reload()
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    app.setApplicationName(APP_TITLE)

    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    db = Database(db_path)

    window = MainWindow(db)
    window.show()

    hud = HUDWidget(db)
    hud.show()

    # Keep a reference so it isn't garbage collected.
    window._hud_ref = hud

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
