"""
hud.py — Ambient Anti-Distraction HUD.

A small, frameless, always-on-top widget that sits pinned to a screen
corner and quietly reminds the user of a short list of focus rules. It
never steals keyboard focus from whatever app the user is actually
working in (Qt.WindowDoesNotAcceptFocus + a non-activating show), can be
dragged by its grip handle, and supports fast inline add/edit/delete of
its rules, all persisted to SQLite via Database.

Design language matches app.py's palette (Deep Midnight Obsidian, Soft
Indigo, Sage Emerald, Coral/Crimson, Muted Gray) — see theme.py.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QIcon, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy, QMenu, QApplication
)

from theme import (
    COLOR_BG, COLOR_SURFACE, COLOR_BORDER, COLOR_INDIGO, COLOR_EMERALD,
    COLOR_CRIMSON, COLOR_MUTED, COLOR_TEXT,
)
from database import Database


CORNER_MARGIN = 18
HUD_WIDTH = 250


class RuleRow(QFrame):
    """One editable anti-distraction rule line."""

    edit_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, rule_id: int, text: str, parent=None):
        super().__init__(parent)
        self.rule_id = rule_id
        self.setObjectName("RuleRow")
        self.setStyleSheet(f"""
            QFrame#RuleRow {{
                background: transparent;
                border-radius: 6px;
            }}
            QFrame#RuleRow:hover {{
                background: {COLOR_BORDER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 6, 5)
        layout.setSpacing(6)

        dot = QLabel("•")
        dot.setStyleSheet(f"color: {COLOR_CRIMSON}; font-size: 13px; background: transparent;")
        layout.addWidget(dot)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 12px; background: transparent;"
        )
        layout.addWidget(self.label, 1)

        self.edit_btn = QPushButton("✎")
        self.edit_btn.setFixedSize(20, 20)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet(self._icon_btn_style(COLOR_INDIGO))
        self.edit_btn.hide()
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.rule_id))
        layout.addWidget(self.edit_btn)

        self.del_btn = QPushButton("✕")
        self.del_btn.setFixedSize(20, 20)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setStyleSheet(self._icon_btn_style(COLOR_CRIMSON))
        self.del_btn.hide()
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.rule_id))
        layout.addWidget(self.del_btn)

    @staticmethod
    def _icon_btn_style(color):
        return f"""
            QPushButton {{
                background: transparent;
                color: {color};
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
            }}
        """

    def enterEvent(self, event):
        self.edit_btn.show()
        self.del_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.edit_btn.hide()
        self.del_btn.hide()
        super().leaveEvent(event)


class EditRow(QFrame):
    """Inline text-edit row shown when adding or editing a rule."""

    submitted = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.edit = QLineEdit(initial_text)
        self.edit.setPlaceholderText("New focus rule…")
        self.edit.setStyleSheet(f"""
            QLineEdit {{
                background: {COLOR_BG};
                color: {COLOR_TEXT};
                border: 1px solid {COLOR_INDIGO};
                border-radius: 5px;
                padding: 4px 7px;
                font-size: 12px;
            }}
        """)
        self.edit.returnPressed.connect(self._submit)
        layout.addWidget(self.edit, 1)

        ok_btn = QPushButton("✓")
        ok_btn.setFixedSize(20, 20)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_EMERALD};
                border: none; font-weight: 700; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); border-radius: 4px; }}
        """)
        ok_btn.clicked.connect(self._submit)
        layout.addWidget(ok_btn)

        cancel_btn = QPushButton("✕")
        cancel_btn.setFixedSize(20, 20)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_MUTED};
                border: none; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); border-radius: 4px; }}
        """)
        cancel_btn.clicked.connect(self.cancelled.emit)
        layout.addWidget(cancel_btn)

    def _submit(self):
        text = self.edit.text().strip()
        if text:
            self.submitted.emit(text)
        else:
            self.cancelled.emit()


class HUDWidget(QWidget):
    """The floating, always-on-top, non-focus-stealing anti-distraction HUD."""

    def __init__(self, db: Database):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.db = db
        self._drag_offset: QPoint | None = None
        self._editing_id: int | None = None  # None = not editing, -1 = adding new
        self._collapsed = self.db.get_hud_state("collapsed", "0") == "1"

        # Never steal keyboard focus from whatever app is active.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._build_ui()
        self._reload_rules()
        self._restore_position()
        self._apply_collapsed_state()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        self.setFixedWidth(HUD_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("HUDCard")
        self.card.setStyleSheet(f"""
            QFrame#HUDCard {{
                background: {COLOR_SURFACE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 14px;
            }}
        """)
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 10)
        card_layout.setSpacing(2)

        # --- grip / header bar (drag handle) ---
        self.grip = QFrame()
        self.grip.setFixedHeight(30)
        self.grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self.grip.setStyleSheet(f"""
            background: transparent;
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
        """)
        grip_layout = QHBoxLayout(self.grip)
        grip_layout.setContentsMargins(12, 6, 8, 4)

        title = QLabel("FOCUS")
        title.setStyleSheet(
            f"color: {COLOR_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 2px; background: transparent;"
        )
        grip_layout.addWidget(title)
        grip_layout.addStretch(1)

        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(20, 20)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_INDIGO};
                border: none; font-size: 15px; font-weight: 700;
            }}
            QPushButton:hover {{ background: rgba(99,102,241,0.15); border-radius: 5px; }}
        """)
        self.add_btn.clicked.connect(self._start_add)
        grip_layout.addWidget(self.add_btn)

        self.collapse_btn = QPushButton("–")
        self.collapse_btn.setFixedSize(20, 20)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_MUTED};
                border: none; font-size: 15px; font-weight: 700;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); border-radius: 5px; }}
        """)
        self.collapse_btn.clicked.connect(self._toggle_collapsed)
        grip_layout.addWidget(self.collapse_btn)

        card_layout.addWidget(self.grip)

        # --- rules list container ---
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 2, 4, 0)
        self.list_layout.setSpacing(1)
        card_layout.addWidget(self.list_container)

        self._editor: EditRow | None = None

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def _reload_rules(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rules = self.db.list_hud_rules()
        if not rules:
            empty = QLabel("No rules yet — click + to add one")
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"color: {COLOR_MUTED}; font-size: 11px; padding: 8px; background: transparent;"
            )
            self.list_layout.addWidget(empty)
            return

        for rule in rules:
            row = RuleRow(rule["id"], rule["text"])
            row.edit_requested.connect(self._start_edit)
            row.delete_requested.connect(self._delete_rule)
            self.list_layout.addWidget(row)

    def _start_add(self):
        self._replace_with_editor(rule_id=-1, initial_text="")

    def _start_edit(self, rule_id: int):
        rules = {r["id"]: r["text"] for r in self.db.list_hud_rules()}
        self._replace_with_editor(rule_id=rule_id, initial_text=rules.get(rule_id, ""))

    def _replace_with_editor(self, rule_id: int, initial_text: str):
        if self._editor is not None:
            return
        self._editing_id = rule_id
        self._editor = EditRow(initial_text)
        self._editor.submitted.connect(self._commit_edit)
        self._editor.cancelled.connect(self._cancel_edit)
        self.list_layout.addWidget(self._editor)
        if self._collapsed:
            self._set_collapsed(False, persist=False)
        # Typing requires real keyboard focus, which the HUD normally
        # refuses (by design, so it never steals focus from other apps).
        # Temporarily allow focus for the duration of the edit only.
        self._allow_focus(True)
        self._editor.edit.setFocus()

    def _commit_edit(self, text: str):
        if self._editing_id == -1:
            self.db.add_hud_rule(text)
        elif self._editing_id is not None:
            self.db.update_hud_rule(self._editing_id, text)
        self._editing_id = None
        self._editor = None
        self._allow_focus(False)
        self._reload_rules()
        self._resize_to_content()

    def _cancel_edit(self):
        self._editing_id = None
        self._editor = None
        self._allow_focus(False)
        self._reload_rules()
        self._resize_to_content()

    def _allow_focus(self, allow: bool):
        """Toggle WindowDoesNotAcceptFocus off/on around inline editing.

        The HUD is normally unfocusable by design (see __init__), but a
        QLineEdit needs real OS-level keyboard focus to accept typing.
        Qt requires the window to be re-shown after a window-flag change
        for it to take effect, so we do that here rather than in the
        edit-row widgets themselves.
        """
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, not allow)
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if allow else Qt.FocusPolicy.NoFocus
        )
        if was_visible:
            self.show()

    def _delete_rule(self, rule_id: int):
        self.db.delete_hud_rule(rule_id)
        self._reload_rules()
        self._resize_to_content()

    # ------------------------------------------------------------------ #
    # Collapse / expand
    # ------------------------------------------------------------------ #
    def _toggle_collapsed(self):
        self._set_collapsed(not self._collapsed)

    def _set_collapsed(self, collapsed: bool, persist: bool = True):
        self._collapsed = collapsed
        self._apply_collapsed_state()
        if persist:
            self.db.set_hud_state("collapsed", "1" if collapsed else "0")

    def _apply_collapsed_state(self):
        self.list_container.setVisible(not self._collapsed)
        self.collapse_btn.setText("+" if self._collapsed else "–")
        self._resize_to_content()

    def _resize_to_content(self):
        self.adjustSize()

    # ------------------------------------------------------------------ #
    # Positioning / dragging
    # ------------------------------------------------------------------ #
    def _restore_position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        default_x = screen.right() - HUD_WIDTH - CORNER_MARGIN
        default_y = screen.top() + CORNER_MARGIN
        x = int(self.db.get_hud_state("pos_x", str(default_x)))
        y = int(self.db.get_hud_state("pos_y", str(default_y)))
        # Clamp onto current screen bounds in case resolution changed.
        x = max(screen.left(), min(x, screen.right() - HUD_WIDTH))
        y = max(screen.top(), min(y, screen.bottom() - 40))
        self.move(x, y)

    def _save_position(self):
        pos = self.pos()
        self.db.set_hud_state("pos_x", str(pos.x()))
        self.db.set_hud_state("pos_y", str(pos.y()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            grip_rect_in_self = self.grip.rect().translated(
                self.grip.mapTo(self, self.grip.rect().topLeft())
            )
            if grip_rect_in_self.contains(event.position().toPoint()):
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._snap_to_nearest_corner()
            self._save_position()
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def _snap_to_nearest_corner(self):
        """Gently snap to whichever screen corner is closest after a drag,
        so the HUD always ends up docked rather than floating mid-screen."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        geo = self.frameGeometry()
        center_x = geo.center().x()
        center_y = geo.center().y()

        target_x = (
            screen.left() + CORNER_MARGIN
            if center_x < screen.center().x()
            else screen.right() - geo.width() - CORNER_MARGIN
        )
        target_y = (
            screen.top() + CORNER_MARGIN
            if center_y < screen.center().y()
            else screen.bottom() - geo.height() - CORNER_MARGIN
        )
        self.move(target_x, target_y)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {COLOR_SURFACE}; color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 14px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {COLOR_INDIGO}; }}
        """)
        toggle_label = "Expand" if self._collapsed else "Collapse"
        act_toggle = menu.addAction(toggle_label)
        act_hide = menu.addAction("Hide HUD")
        chosen = menu.exec(event.globalPos())
        if chosen == act_toggle:
            self._toggle_collapsed()
        elif chosen == act_hide:
            self.hide()
