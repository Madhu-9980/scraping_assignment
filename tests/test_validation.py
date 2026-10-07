"""Tests for processing/validation.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from processing.validation import (  # noqa: E402
    rejection_reason_counts,
    validate_record,
    validate_records,
)


def valid_book_record(**overrides) -> dict:
    record = {
        "source": config.BOOKS_SOURCE,
        "source_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "name_or_title": "A Light in the Attic",
        "category": "Poetry",
        "price": 51.77,
        "rating": 3,
        "author": None,
        "tags": None,
        "description": "A collection of poetry.",
        "scraped_at": "2026-10-06T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def valid_quote_record(**overrides) -> dict:
    record = {
        "source": config.QUOTES_SOURCE,
        "source_url": "https://quotes.toscrape.com/page/1/",
        "name_or_title": "“A quote about thinking.”",
        "category": None,
        "price": None,
        "rating": None,
        "author": "Albert Einstein",
        "tags": "thinking; world",
        "description": None,
        "scraped_at": "2026-10-06T00:00:00+00:00",
    }
    record.update(overrides)
    return record


class TestValidRecords:
    def test_valid_book_passes(self):
        assert validate_record(valid_book_record()) == []

    def test_valid_quote_passes(self):
        assert validate_record(valid_quote_record()) == []


class TestInvalidRecords:
    def test_unknown_source_rejected(self):
        reasons = validate_record(valid_book_record(source="Wikipedia"))
        assert any(r.startswith("unknown_source") for r in reasons)

    def test_missing_title_rejected(self):
        reasons = validate_record(valid_book_record(name_or_title=""))
        assert "missing_name_or_title" in reasons

    def test_missing_title_none_rejected(self):
        reasons = validate_record(valid_book_record(name_or_title=None))
        assert "missing_name_or_title" in reasons

    def test_invalid_url_rejected(self):
        reasons = validate_record(valid_book_record(source_url="not-a-url"))
        assert any(r.startswith("invalid_source_url") for r in reasons)

    def test_missing_url_rejected(self):
        reasons = validate_record(valid_book_record(source_url=None))
        assert any(r.startswith("invalid_source_url") for r in reasons)

    def test_non_numeric_price_rejected(self):
        reasons = validate_record(valid_book_record(price=None))
        assert any(r.startswith("price_not_numeric") for r in reasons)

    def test_negative_price_rejected(self):
        reasons = validate_record(valid_book_record(price=-5.0))
        assert any(r.startswith("price_not_positive") for r in reasons)

    def test_rating_out_of_range_rejected(self):
        reasons = validate_record(valid_book_record(rating=9))
        assert any(r.startswith("rating_out_of_range") for r in reasons)

    def test_missing_rating_rejected(self):
        reasons = validate_record(valid_book_record(rating=None))
        assert any(r.startswith("rating_out_of_range") for r in reasons)

    def test_quote_without_author_rejected(self):
        reasons = validate_record(valid_quote_record(author=""))
        assert "missing_author" in reasons

    def test_missing_timestamp_rejected(self):
        reasons = validate_record(valid_book_record(scraped_at=None))
        assert "missing_scraped_at" in reasons


class TestValidateRecords:
    def test_split_into_valid_and_rejected(self):
        records = [
            valid_book_record(),
            valid_book_record(name_or_title=""),
            valid_quote_record(),
            valid_quote_record(author=None),
        ]
        valid, rejected = validate_records(records)

        assert len(valid) == 2
        assert len(rejected) == 2
        assert all("reasons" in entry for entry in rejected)
        assert all(isinstance(entry["reasons"], list) for entry in rejected)

    def test_reason_counts_aggregated(self):
        records = [
            valid_book_record(price=None),
            valid_book_record(price=None),
            valid_book_record(name_or_title=""),
        ]
        _, rejected = validate_records(records)
        counts = rejection_reason_counts(rejected)

        assert counts["price_not_numeric"] == 2
        assert counts["missing_name_or_title"] == 1
