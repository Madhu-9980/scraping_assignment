"""Tests for processing/deduplication.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from processing.deduplication import (  # noqa: E402
    dedup_key,
    deduplicate,
    normalize_for_dedup,
)


def book(title: str, source: str = config.BOOKS_SOURCE, url: str = "") -> dict:
    return {
        "source": source,
        "source_url": url or f"https://books.toscrape.com/catalogue/{title.lower()}.html",
        "name_or_title": title,
    }


class TestNormalizeForDedup:
    def test_whitespace_and_case_variants_collapse(self):
        variants = [
            "Example Book Title",
            " Example Book Title ",
            "EXAMPLE BOOK TITLE",
            "example   book title",
            "example\tbook\n title",
        ]
        keys = {normalize_for_dedup(v) for v in variants}
        assert keys == {"example book title"}

    def test_curly_quotes_and_punctuation_removed(self):
        # The quotes site wraps text in typographic quotes.
        a = normalize_for_dedup("“The world as we have created it.”")
        b = normalize_for_dedup('"The world as we have created it."')
        assert a == b
        assert "“" not in a and "”" not in a

    def test_apostrophes_folded(self):
        assert normalize_for_dedup("Shakespeare's Sonnets") == normalize_for_dedup(
            "Shakespeares Sonnets"
        )

    def test_none_becomes_empty(self):
        assert normalize_for_dedup(None) == ""


class TestDedupKey:
    def test_key_scoped_by_source(self):
        same_text_different_source = dedup_key(
            {"source": config.QUOTES_SOURCE, "name_or_title": "Same text"}
        ) != dedup_key({"source": config.BOOKS_SOURCE, "name_or_title": "Same text"})
        assert same_text_different_source

    def test_key_format(self):
        assert dedup_key(book("A Light in the Attic")) == (
            "books to scrape::a light in the attic"
        )


class TestDeduplicate:
    def test_case_and_whitespace_duplicates_removed(self):
        records = [
            book(" Example Book Title ", url="https://example.com/1"),
            book("EXAMPLE BOOK TITLE", url="https://example.com/2"),
            book("example   book title", url="https://example.com/3"),
            book("Another Book", url="https://example.com/4"),
        ]
        unique, dropped = deduplicate(records)

        assert len(unique) == 2
        assert len(dropped) == 2
        # First occurrence is preserved.
        assert unique[0]["source_url"] == "https://example.com/1"

    def test_different_titles_not_dropped(self):
        records = [book("Book One"), book("Book Two"), book("Book Three")]
        unique, dropped = deduplicate(records)
        assert len(unique) == 3
        assert dropped == []

    def test_cross_source_same_text_kept(self):
        records = [
            {"source": config.BOOKS_SOURCE, "name_or_title": "Same Text"},
            {"source": config.QUOTES_SOURCE, "name_or_title": "Same Text"},
        ]
        unique, dropped = deduplicate(records)
        assert len(unique) == 2
        assert dropped == []

    def test_dropped_rows_reference_original(self):
        records = [
            book("Dup", url="https://example.com/original"),
            book("  DUP ", url="https://example.com/copy"),
        ]
        _, dropped = deduplicate(records)
        assert dropped[0]["duplicate_of"] == "https://example.com/original"
        assert dropped[0]["source_url"] == "https://example.com/copy"

    def test_empty_keys_never_match(self):
        records = [
            {"source": config.BOOKS_SOURCE, "name_or_title": "", "source_url": "a"},
            {"source": config.BOOKS_SOURCE, "name_or_title": "", "source_url": "b"},
        ]
        unique, dropped = deduplicate(records)
        assert len(unique) == 2
        assert dropped == []
