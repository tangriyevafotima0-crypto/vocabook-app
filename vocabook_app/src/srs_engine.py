"""
srs_engine.py — SuperMemo-2 (SM-2) spaced repetition scheduling.

The engine is pure and stateless: given a card's current SRS state and a
user rating, it returns the next state. It does not touch the database;
app.py is responsible for persisting the result via Database.update_card_srs.

Rating scale (mapped internally to the classic SM-2 quality 0-5 scale):
    AGAIN -> quality 0   Full lapse. Reset repetitions, interval -> 1 day.
    HARD  -> quality 3   Recalled, but with real difficulty.
    GOOD  -> quality 4   Recalled correctly with normal effort.
    EASY  -> quality 5   Recalled effortlessly.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum


class Rating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


_QUALITY_MAP = {
    Rating.AGAIN: 0,
    Rating.HARD: 3,
    Rating.GOOD: 4,
    Rating.EASY: 5,
}

MIN_EASE_FACTOR = 1.3


@dataclass
class SRSState:
    interval: float          # days
    ease_factor: float
    repetitions: int
    box_level: int           # 0..5, cosmetic "Leitner-style" bucket for the UI


@dataclass
class SRSResult(SRSState):
    due_date: str             # ISO date string
    correct: bool


def _clamp_ease(ef: float) -> float:
    return max(MIN_EASE_FACTOR, ef)


def schedule(state: SRSState, rating: Rating, today: datetime.date = None) -> SRSResult:
    """Compute the next SRS state for a card given the user's rating.

    Follows the standard SM-2 recurrence:
        EF' = EF + (0.1 - (5-q)*(0.08 + (5-q)*0.02))
        if q < 3: repetitions = 0, interval = 1
        else:
            repetitions += 1
            if repetitions == 1: interval = 1
            elif repetitions == 2: interval = 6
            else: interval = round(previous_interval * EF')

    HARD and EASY additionally scale the resulting interval slightly so the
    four buttons feel meaningfully distinct in a UI (this is a common,
    widely-used refinement on top of vanilla SM-2 and does not change the
    algorithm's convergence behavior).
    """
    if today is None:
        today = datetime.date.today()

    q = _QUALITY_MAP[rating]
    ef = state.ease_factor
    new_ef = _clamp_ease(ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))

    if q < 3:
        # Lapse: start over, but keep the (slightly penalized) ease factor.
        new_reps = 0
        new_interval = 1.0
        box_level = max(0, state.box_level - 1)
        correct = False
    else:
        new_reps = state.repetitions + 1
        if new_reps == 1:
            new_interval = 1.0
        elif new_reps == 2:
            new_interval = 6.0
        else:
            new_interval = round(state.interval * new_ef, 2)

        # Distinct pacing per button, layered on top of SM-2's core interval.
        if rating == Rating.HARD:
            new_interval = max(1.0, round(new_interval * 0.7, 2))
        elif rating == Rating.EASY:
            new_interval = round(new_interval * 1.3, 2)

        box_level = min(5, state.box_level + 1)
        correct = True

    due = today + datetime.timedelta(days=max(1, round(new_interval)))

    return SRSResult(
        interval=new_interval,
        ease_factor=new_ef,
        repetitions=new_reps,
        box_level=box_level,
        due_date=due.isoformat(),
        correct=correct,
    )


def state_from_row(row) -> SRSState:
    """Build an SRSState from a sqlite3.Row (cards table)."""
    return SRSState(
        interval=row["interval"],
        ease_factor=row["ease_factor"],
        repetitions=row["repetitions"],
        box_level=row["box_level"],
    )
