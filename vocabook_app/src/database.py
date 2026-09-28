"""
database.py — SQLite persistence layer for Vocabook.

Owns schema creation and every read/write query used by the rest of the
application. No other module should touch sqlite3 directly; they should
go through the Database class so storage concerns stay in one place.
"""

from __future__ import annotations

import sqlite3
import datetime
import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flashcards.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    set_number INTEGER NOT NULL,
    total_words INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(book_id, set_number)
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    example TEXT,
    antonym TEXT,

    -- SM-2 state
    interval REAL NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    repetitions INTEGER NOT NULL DEFAULT 0,
    box_level INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL,
    last_reviewed TEXT,
    total_reviews INTEGER NOT NULL DEFAULT 0,
    total_correct INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cards_set_id ON cards(set_id);
CREATE INDEX IF NOT EXISTS idx_cards_due_date ON cards(due_date);

CREATE TABLE IF NOT EXISTS hud_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hud_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);
"""

DEFAULT_HUD_RULES = [
    "No social media during Deep Work",
    "No maladaptive daydreaming",
    "Close unrelated tabs",
    "One task at a time",
]


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class CardRow:
    id: int
    set_id: int
    word: str
    definition: str
    example: Optional[str]
    antonym: Optional[str]
    interval: float
    ease_factor: float
    repetitions: int
    box_level: int
    due_date: str
    last_reviewed: Optional[str]
    total_reviews: int
    total_correct: int


class Database:
    """Thin, explicit wrapper around the app's SQLite file."""

    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def _init_schema(self):
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        cur = self._conn.execute("SELECT COUNT(*) FROM hud_rules")
        if cur.fetchone()[0] == 0:
            self.seed_default_hud_rules()

    def seed_default_hud_rules(self):
        ts = now_iso()
        for i, text in enumerate(DEFAULT_HUD_RULES):
            self._conn.execute(
                "INSERT INTO hud_rules (text, sort_order, created_at) VALUES (?, ?, ?)",
                (text, i, ts),
            )
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Books / Sets
    # ------------------------------------------------------------------ #
    def get_or_create_book(self, title: str, sort_order: int = 0) -> int:
        cur = self._conn.execute("SELECT id FROM books WHERE title = ?", (title,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = self._conn.execute(
            "INSERT INTO books (title, sort_order) VALUES (?, ?)", (title, sort_order)
        )
        self._conn.commit()
        return cur.lastrowid

    def get_or_create_set(self, book_id: int, title: str, set_number: int) -> int:
        cur = self._conn.execute(
            "SELECT id FROM sets WHERE book_id = ? AND set_number = ?",
            (book_id, set_number),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = self._conn.execute(
            "INSERT INTO sets (book_id, title, set_number, total_words, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (book_id, title, set_number, now_iso()),
        )
        self._conn.commit()
        return cur.lastrowid

    def bump_set_total_words(self, set_id: int, delta: int = 1):
        self._conn.execute(
            "UPDATE sets SET total_words = total_words + ? WHERE id = ?",
            (delta, set_id),
        )
        self._conn.commit()

    def list_books(self):
        return self._conn.execute(
            "SELECT * FROM books ORDER BY sort_order, id"
        ).fetchall()

    def list_sets_for_book(self, book_id: int):
        return self._conn.execute(
            "SELECT * FROM sets WHERE book_id = ? ORDER BY set_number", (book_id,)
        ).fetchall()

    def list_all_sets_with_books(self):
        """Every set joined with its parent book, ordered for TOC display."""
        return self._conn.execute(
            """
            SELECT sets.*, books.title AS book_title, books.sort_order AS book_sort
            FROM sets
            JOIN books ON books.id = sets.book_id
            ORDER BY books.sort_order, sets.set_number
            """
        ).fetchall()

    def set_mastery(self, set_id: int) -> float:
        """Percentage (0-100) of cards in a set considered 'mastered'
        (repetitions >= 2 and ease_factor >= 2.5 is our working definition)."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM cards WHERE set_id = ?", (set_id,)
        ).fetchone()
        total = row["total"]
        if total == 0:
            return 0.0
        mastered = self._conn.execute(
            "SELECT COUNT(*) AS c FROM cards WHERE set_id = ? AND repetitions >= 2",
            (set_id,),
        ).fetchone()["c"]
        return round(100.0 * mastered / total, 1)

    def set_due_count(self, set_id: int) -> int:
        today = datetime.date.today().isoformat()
        return self._conn.execute(
            "SELECT COUNT(*) AS c FROM cards WHERE set_id = ? AND due_date <= ?",
            (set_id, today),
        ).fetchone()["c"]

    # ------------------------------------------------------------------ #
    # Cards
    # ------------------------------------------------------------------ #
    def insert_card(self, set_id: int, word: str, definition: str,
                     example: str = "", antonym: str = ""):
        today = datetime.date.today().isoformat()
        self._conn.execute(
            """
            INSERT INTO cards (set_id, word, definition, example, antonym,
                                interval, ease_factor, repetitions, box_level,
                                due_date, total_reviews, total_correct)
            VALUES (?, ?, ?, ?, ?, 0, 2.5, 0, 0, ?, 0, 0)
            """,
            (set_id, word, definition, example, antonym, today),
        )

    def commit(self):
        self._conn.commit()

    def card_exists(self, set_id: int, word: str) -> bool:
        row = self._conn.execute(
            "SELECT id FROM cards WHERE set_id = ? AND word = ?", (set_id, word)
        ).fetchone()
        return row is not None

    def get_cards_for_set(self, set_id: int):
        return self._conn.execute(
            "SELECT * FROM cards WHERE set_id = ? ORDER BY id", (set_id,)
        ).fetchall()

    def get_due_cards_for_set(self, set_id: int, limit: int = 200):
        today = datetime.date.today().isoformat()
        return self._conn.execute(
            "SELECT * FROM cards WHERE set_id = ? AND due_date <= ? "
            "ORDER BY due_date LIMIT ?",
            (set_id, today, limit),
        ).fetchall()

    def get_card(self, card_id: int):
        return self._conn.execute(
            "SELECT * FROM cards WHERE id = ?", (card_id,)
        ).fetchone()

    def update_card_srs(self, card_id: int, interval: float, ease_factor: float,
                         repetitions: int, box_level: int, due_date: str,
                         correct: bool):
        self._conn.execute(
            """
            UPDATE cards
            SET interval = ?, ease_factor = ?, repetitions = ?, box_level = ?,
                due_date = ?, last_reviewed = ?, total_reviews = total_reviews + 1,
                total_correct = total_correct + ?
            WHERE id = ?
            """,
            (interval, ease_factor, repetitions, box_level, due_date, now_iso(),
             1 if correct else 0, card_id),
        )
        self._conn.commit()

    def log_review(self, card_id: int, rating: str):
        self._conn.execute(
            "INSERT INTO review_log (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
            (card_id, rating, now_iso()),
        )
        self._conn.commit()

    def total_card_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM cards").fetchone()["c"]

    def global_due_count(self) -> int:
        today = datetime.date.today().isoformat()
        return self._conn.execute(
            "SELECT COUNT(*) AS c FROM cards WHERE due_date <= ?", (today,)
        ).fetchone()["c"]

    # ------------------------------------------------------------------ #
    # HUD
    # ------------------------------------------------------------------ #
    def list_hud_rules(self):
        return self._conn.execute(
            "SELECT * FROM hud_rules ORDER BY sort_order, id"
        ).fetchall()

    def add_hud_rule(self, text: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM hud_rules"
        ).fetchone()
        next_order = row["n"]
        cur = self._conn.execute(
            "INSERT INTO hud_rules (text, sort_order, created_at) VALUES (?, ?, ?)",
            (text, next_order, now_iso()),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_hud_rule(self, rule_id: int, text: str):
        self._conn.execute(
            "UPDATE hud_rules SET text = ? WHERE id = ?", (text, rule_id)
        )
        self._conn.commit()

    def delete_hud_rule(self, rule_id: int):
        self._conn.execute("DELETE FROM hud_rules WHERE id = ?", (rule_id,))
        self._conn.commit()

    def reorder_hud_rule(self, rule_id: int, new_order: int):
        self._conn.execute(
            "UPDATE hud_rules SET sort_order = ? WHERE id = ?", (new_order, rule_id)
        )
        self._conn.commit()

    def get_hud_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM hud_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_hud_state(self, key: str, value: str):
        self._conn.execute(
            "INSERT INTO hud_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()
