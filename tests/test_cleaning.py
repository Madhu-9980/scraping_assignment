"""Tests for processing/cleaning.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing.cleaning import (  # noqa: E402
    clean_record,
    clean_text,
    normalize_url,
    parse_price,
    parse_rating,
    parse_tags,
    utc_timestamp,
)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------
class TestCleanText:
    def test_collapses_internal_whitespace(self):
        assert clean_text("  A   Light\n in\tthe  Attic ") == "A Light in the Attic"

    def test_nFKC_normalization(self):
        # full-width characters folded to ASCII
        assert clean_text("ＴＥＳＴ") == "TEST"

    def test_non_breaking_space_removed(self):
        assert clean_text("Hello\u00a0World") == "Hello World"

    def test_empty_returns_none(self):
        assert clean_text("   ") is None

    def test_none_returns_none(self):
        assert clean_text(None) is None

    def test_number_coerced_to_string(self):
        assert clean_text(42) == "42"


# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------
class TestParsePrice:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("£51.77", 51.77),
            ("$1,234.50", 1234.50),
            ("€13.99", 13.99),
            ("51.77", 51.77),
            (51.77, 51.77),
            (22, 22.0),
            ("  £9.99  ", 9.99),
        ],
    )
    def test_valid_prices(self, raw, expected):
        assert parse_price(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", [None, "", "N/A", "free", "£", []])
    def test_invalid_prices_return_none(self, raw):
        assert parse_price(raw) is None


# ---------------------------------------------------------------------------
# parse_rating
# ---------------------------------------------------------------------------
class TestParseRating:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Three", 3),
            ("One", 1),
            ("Five", 5),
            ("star-rating Four", 4),
            ("two", 2),
            (4, 4),
            ("4", 4),
            ("3/5", 3),
        ],
    )
    def test_valid_ratings(self, raw, expected):
        assert parse_rating(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "ten", "star-rating", 0, 6, 99])
    def test_invalid_ratings_return_none(self, raw):
        assert parse_rating(raw) is None


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------
class TestNormalizeUrl:
    def test_relative_url_joined_with_base(self):
        # Real markup: hrefs are relative to the page they appear on
        # (page-2.html links look like "in-her-wake_980/index.html").
        url = normalize_url(
            "in-her-wake_980/index.html",
            "https://books.toscrape.com/catalogue/page-2.html",
        )
        assert url == "https://books.toscrape.com/catalogue/in-her-wake_980/index.html"

    def test_index_page_href_joined(self):
        url = normalize_url(
            "catalogue/a-light-in-the-attic_1000/index.html",
            "https://books.toscrape.com/index.html",
        )
        assert url == (
            "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )

    def test_fragment_stripped(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_invalid_url_returns_none(self):
        assert normalize_url("not a url") is None
        assert normalize_url("ftp://example.com/x") is None
        assert normalize_url("") is None
        assert normalize_url(None) is None


# ---------------------------------------------------------------------------
# parse_tags
# ---------------------------------------------------------------------------
class TestParseTags:
    def test_list_joined(self):
        assert parse_tags(["change", "thinking"]) == "change; thinking"

    def test_list_with_whitespace_entries(self):
        assert parse_tags([" change ", "", "world"]) == "change; world"

    def test_none_returns_none(self):
        assert parse_tags(None) is None

    def test_empty_list_returns_none(self):
        assert parse_tags([]) is None

    def test_string_passed_through_cleaned(self):
        assert parse_tags("  life; love  ") == "life; love"


# ---------------------------------------------------------------------------
# clean_record
# ---------------------------------------------------------------------------
class TestCleanRecord:
    def test_book_record_end_to_end(self):
        raw = {
            "source": "Books to Scrape",
            "source_url": "catalogue/a-light-in-the-attic_1000/index.html",
            "name_or_title": "  A Light   in the Attic ",
            "category": " Poetry ",
            "price": "£51.77",
            "rating": "star-rating Three",
            "author": None,
            "tags": None,
            "description": "  A classic collection. ",
            "listing_page_url": "https://books.toscrape.com/index.html",
        }
        cleaned = clean_record(raw)

        assert cleaned["source_url"] == (
            "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )
        assert cleaned["name_or_title"] == "A Light in the Attic"
        assert cleaned["category"] == "Poetry"
        assert cleaned["price"] == pytest.approx(51.77)
        assert cleaned["rating"] == 3
        assert cleaned["author"] is None
        assert cleaned["description"] == "A classic collection."
        assert cleaned["scraped_at"]  # timestamp added

    def test_quote_record_keeps_nuls(self):
        raw = {
            "source": "Quotes to Scrape",
            "source_url": "https://quotes.toscrape.com/page/1/",
            "name_or_title": "“A quote.”",
            "category": None,
            "price": None,
            "rating": None,
            "author": "Albert Einstein",
            "tags": ["life", "love"],
            "description": None,
        }
        cleaned = clean_record(raw)

        assert cleaned["price"] is None
        assert cleaned["rating"] is None
        assert cleaned["category"] is None
        assert cleaned["tags"] == "life; love"
        assert cleaned["author"] == "Albert Einstein"

    def test_timestamp_is_iso_format(self):
        stamp = utc_timestamp()
        assert "T" in stamp and (stamp.endswith("+00:00") or stamp.endswith("Z"))
