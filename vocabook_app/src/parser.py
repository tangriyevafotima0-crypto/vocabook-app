"""
parser.py — Automated vocabulary-book ingestion for Vocabook.

Tailored to the structure of "Vocabook_30.pdf" (a multi-book SAT
vocabulary compilation: College Panda 400 Words, Ivy Global 500 Words,
Advanced Package Vocabulary, and SATashkent Words), but written generally
enough to survive re-exports/re-ordering of the same source, or a
similarly-structured book (numbered "Word / Definition / Example /
Antonym" tables grouped into "Set N" chapters under book-title headers).

Strategy
--------
1. Walk every page's extracted text looking for two kinds of markers:
   - a bold book-title line, quoted like `"College Panda 400 Words"`
   - a `Set N` line marking the start of a new set within the current book
2. On every page, additionally pull the page's data table(s) via
   pdfplumber's table extraction (works reliably here because the source
   book renders vocabulary entries as real PDF tables, not styled text).
3. Because a set's table frequently spans a page break, rows are merged
   using the numeric `#` column: a row with a blank `#` is a continuation
   of the previous row's `Example` cell, not a new word.
4. Word rows are only accepted while we are inside a book's numbered
   "Learning Time" table region. Once row numbers stop increasing (e.g.
   because we've reached a Reading Time passage or Words-in-Context quiz
   page with its own unrelated table), we stop collecting for that page
   position, but keep scanning subsequent pages for the next `Set N`
   marker.
5. Stops entirely once all four known book title regions have been
   consumed (guards against accidentally ingesting the Answers /
   Prefix-Suffix appendix, which uses a different, incompatible table
   shape).

This module can be run standalone:  `python parser.py [pdf_path] [db_path]`
"""

from __future__ import annotations

import re
import sys
import os

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import Database, DEFAULT_DB_PATH  # noqa: E402


BOOK_TITLE_RE = re.compile(r'^[“"](?P<title>.+?)[”"]\s*$')
SET_LINE_RE = re.compile(r'^Set\s+(\d+)\s*$')
EXPECTED_HEADER = ("#", "Word", "Definition", "Example", "Antonym")

# Titles that look like a quoted "book header" but are actually appendix
# material with an incompatible table shape (Word Part / Meaning / ... for
# Prefix-Suffix) or no vocabulary table at all. Ingestion stops for good
# once one of these is seen as a real header line.
STOP_TITLES = {"prefix/suffix"}


def _clean_cell(cell: str) -> str:
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell).strip()


def _is_header_row(row) -> bool:
    cells = tuple(_clean_cell(c) for c in row[:5])
    return cells == EXPECTED_HEADER


def _row_number(row) -> int | None:
    """Return the leading integer in the '#' column, or None if the row
    doesn't start a new word (i.e. it's a wrapped continuation row)."""
    cell = _clean_cell(row[0]) if row else ""
    if cell.isdigit():
        return int(cell)
    return None


class ParsedCard:
    __slots__ = ("word", "definition", "example", "antonym")

    def __init__(self, word, definition, example, antonym):
        self.word = word
        self.definition = definition
        self.example = example
        self.antonym = antonym


class ParsedSet:
    def __init__(self, book_title: str, set_number: int):
        self.book_title = book_title
        self.set_number = set_number
        self.cards: list[ParsedCard] = []

    @property
    def title(self):
        return f"Set {self.set_number}"


def parse_pdf(pdf_path: str, progress_cb=None) -> list[ParsedSet]:
    """Parse the vocabulary PDF into an ordered list of ParsedSet objects.

    progress_cb, if given, is called as progress_cb(current_page, total_pages).
    """
    sets: list[ParsedSet] = []
    current_book = None
    current_set: ParsedSet | None = None
    pending_row: list | None = None  # row awaiting continuation merges

    def flush_pending():
        nonlocal pending_row
        if pending_row is not None and current_set is not None:
            word = _clean_cell(pending_row[1])
            definition = _clean_cell(pending_row[2])
            example = _clean_cell(pending_row[3])
            antonym = _clean_cell(pending_row[4]) if len(pending_row) > 4 else ""
            if word and definition:
                current_set.cards.append(
                    ParsedCard(word, definition, example, antonym)
                )
        pending_row = None

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            # --- detect book / set markers ---
            # A genuine book-title header is always the very first line of
            # its page, immediately followed by "Set 1" as the second line
            # (verified against this book's structure). Quoted titles that
            # show up elsewhere on a page (e.g. a "Reading Time" passage
            # title like "Cultural Impacts of Migration...") must NOT be
            # mistaken for a new book, or all of that book's remaining
            # sets get silently swallowed into a fake "book".
            if lines:
                m = BOOK_TITLE_RE.match(lines[0])
                if m:
                    title = m.group("title").strip()
                    if title.lower() in STOP_TITLES:
                        # Appendix reached (e.g. Prefix/Suffix) — its table
                        # has a different, incompatible shape. Stop parsing
                        # entirely so none of it leaks into the previous
                        # real set.
                        flush_pending()
                        current_book = None
                        current_set = None
                        break
                    if len(lines) > 1 and SET_LINE_RE.match(lines[1]):
                        flush_pending()
                        current_book = title
                        current_set = None

            for line in lines[:2]:
                m2 = SET_LINE_RE.match(line)
                if m2 and current_book is not None:
                    flush_pending()
                    set_num = int(m2.group(1))
                    current_set = ParsedSet(current_book, set_num)
                    sets.append(current_set)

            # --- pull table rows on this page, if we're inside a set ---
            if current_set is not None:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    start_idx = 1 if _is_header_row(table[0]) else 0
                    sample = table[start_idx] if len(table) > start_idx else None
                    if sample is None or len(sample) < 5:
                        continue
                    # Reject tables whose header row is present but doesn't
                    # match our known 5-column vocab schema (guards against
                    # e.g. Prefix/Suffix's differently-labeled columns). A
                    # row that is blank (mid-page continuation from a page
                    # break) or a genuine numbered word row is fine.
                    first_cell = _clean_cell(table[0][0]) if table[0] else ""
                    if first_cell and not (first_cell.isdigit() or first_cell == "#"):
                        continue
                    for row in table[start_idx:]:
                        if len(row) < 5:
                            continue
                        num = _row_number(row)
                        if num is not None:
                            flush_pending()
                            pending_row = list(row)
                        else:
                            # continuation of previous row's example text
                            if pending_row is not None:
                                extra = _clean_cell(row[3]) if len(row) > 3 else ""
                                if extra:
                                    pending_row[3] = (
                                        _clean_cell(pending_row[3]) + " " + extra
                                    )

            if progress_cb:
                progress_cb(page_index + 1, total)

    flush_pending()
    # Drop any sets that ended up empty (e.g. a stray "Set N" match inside
    # prose rather than a real chapter heading).
    return [s for s in sets if s.cards]


def seed_database(pdf_path: str, db_path: str = DEFAULT_DB_PATH,
                   progress_cb=None) -> dict:
    """Parse the PDF and insert everything into SQLite (idempotent —
    re-running will not duplicate books/sets/cards that already exist).

    Returns a small summary dict for logging / CLI output.
    """
    parsed_sets = parse_pdf(pdf_path, progress_cb=progress_cb)

    db = Database(db_path)
    book_order: dict[str, int] = {}
    books_created = 0
    sets_created = 0
    cards_created = 0

    for pset in parsed_sets:
        if pset.book_title not in book_order:
            book_order[pset.book_title] = len(book_order)
            books_created += 1
        book_id = db.get_or_create_book(pset.book_title, book_order[pset.book_title])
        set_id = db.get_or_create_set(book_id, pset.title, pset.set_number)
        sets_created += 1
        for card in pset.cards:
            if not db.card_exists(set_id, card.word):
                db.insert_card(set_id, card.word, card.definition,
                                card.example, card.antonym)
                db.bump_set_total_words(set_id, 1)
                cards_created += 1
    db.commit()
    db.close()

    return {
        "books": len(book_order),
        "sets": sets_created,
        "cards_inserted": cards_created,
        "total_parsed_cards": sum(len(s.cards) for s in parsed_sets),
    }


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PDF = os.path.join(_PROJECT_ROOT, "assets", "vocabulary_source.pdf")

if __name__ == "__main__":
    pdf_arg = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PDF
    db_arg = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB_PATH

    def _progress(cur, total):
        if cur % 20 == 0 or cur == total:
            print(f"  parsing page {cur}/{total}...", file=sys.stderr)

    print(f"Ingesting '{pdf_arg}' -> '{db_arg}'")
    summary = seed_database(pdf_arg, db_arg, progress_cb=_progress)
    print(
        f"Done. Books: {summary['books']}  Sets: {summary['sets']}  "
        f"New cards inserted: {summary['cards_inserted']} "
        f"(parsed {summary['total_parsed_cards']} total entries)"
    )
