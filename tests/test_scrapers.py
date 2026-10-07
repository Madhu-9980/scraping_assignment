"""Offline parsing tests for the scrapers (run against saved HTML fixtures)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from scrapers.books_scraper import (  # noqa: E402
    find_next_page as books_find_next_page,
    normalize_source_url,
    parse_detail_page,
    parse_listing_page,
)
from scrapers.quotes_scraper import (  # noqa: E402
    find_next_page as quotes_find_next_page,
    parse_quotes_page,
)

FIXTURES = Path(__file__).parent / "fixtures"

BOOKS_LISTING_URL = "https://books.toscrape.com/index.html"
QUOTES_LISTING_URL = "https://quotes.toscrape.com/"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Books listing
# ---------------------------------------------------------------------------
class TestBooksListing:
    def setup_method(self):
        self.records = parse_listing_page(load_fixture("books_listing.html"), BOOKS_LISTING_URL)

    def test_record_count(self):
        assert len(self.records) == 2

    def test_full_title_from_title_attribute(self):
        # Anchor text is truncated on the real site; the title attribute is not.
        assert self.records[0]["name_or_title"] == "A Light in the Attic"
        assert self.records[1]["name_or_title"] == "Tipping the Velvet"

    def test_relative_url_absolutised(self):
        assert self.records[0]["source_url"] == (
            "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )

    def test_price_kept_as_raw_text(self):
        # Cleaning happens later – the scraper only extracts.
        assert self.records[0]["price"] == "£51.77"

    def test_rating_word_extracted_from_class(self):
        assert self.records[0]["rating"] == "Three"
        assert self.records[1]["rating"] == "One"

    def test_source_name_set(self):
        assert all(r["source"] == config.BOOKS_SOURCE for r in self.records)

    def test_detail_only_fields_are_none(self):
        assert all(r["category"] is None for r in self.records)
        assert all(r["description"] is None for r in self.records)

    def test_availability_captured(self):
        assert "In stock" in self.records[0]["availability"]

    def test_missing_elements_do_not_crash(self):
        # A product pod lacking price/rating is skipped or partially parsed.
        html = '<article class="product_pod"><h3><a href="x.html" title="X">X</a></h3></article>'
        records = parse_listing_page(html, BOOKS_LISTING_URL)
        assert len(records) == 1
        assert records[0]["price"] == ""
        assert records[0]["rating"] == ""

    def test_garbage_html_returns_empty_list(self):
        assert parse_listing_page("<html><body>nothing here</body></html>", BOOKS_LISTING_URL) == []


# ---------------------------------------------------------------------------
# Books pagination & detail
# ---------------------------------------------------------------------------
class TestBooksPagination:
    def test_next_page_found(self):
        html = load_fixture("books_listing.html")
        assert books_find_next_page(html, BOOKS_LISTING_URL) == (
            "https://books.toscrape.com/catalogue/page-2.html"
        )

    def test_no_next_link_returns_none(self):
        assert books_find_next_page("<html><body>end</body></html>", BOOKS_LISTING_URL) is None

    def test_normalize_source_url(self):
        assert normalize_source_url("catalogue/page-2.html", BOOKS_LISTING_URL) == (
            "https://books.toscrape.com/catalogue/page-2.html"
        )


class TestBooksDetail:
    def setup_method(self):
        self.details = parse_detail_page(
            load_fixture("books_detail.html"),
            "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        )

    def test_category_from_breadcrumb(self):
        # "Home" and the active (title) entry are excluded -> last crumb wins.
        assert self.details["category"] == "Poetry"

    def test_description_extracted(self):
        assert self.details["description"].startswith("It's hard to imagine a world")

    def test_missing_description_returns_none(self):
        details = parse_detail_page(
            '<ul class="breadcrumb"><li class="active">X</li></html>',
            "https://books.toscrape.com/x.html",
        )
        assert details["category"] is None
        assert details["description"] is None


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------
class TestQuotesListing:
    def setup_method(self):
        self.records = parse_quotes_page(load_fixture("quotes_listing.html"), QUOTES_LISTING_URL)

    def test_record_count(self):
        assert len(self.records) == 2

    def test_text_and_author(self):
        assert self.records[0]["name_or_title"].startswith("“The world as we have created it")
        assert self.records[0]["author"] == "Albert Einstein"
        assert self.records[1]["author"] == "J.K. Rowling"

    def test_tags_parsed_as_list(self):
        assert self.records[0]["tags"] == ["change", "deep-thoughts", "thinking", "world"]
        assert self.records[1]["tags"] == ["abilities", "choices"]

    def test_author_url_absolutised(self):
        assert self.records[0]["author_url"] == "https://quotes.toscrape.com/author/Albert-Einstein"

    def test_source_url_is_page_url(self):
        assert all(r["source_url"] == QUOTES_LISTING_URL for r in self.records)

    def test_not_applicable_fields_are_none(self):
        for record in self.records:
            assert record["price"] is None
            assert record["rating"] is None
            assert record["category"] is None
            assert record["description"] is None

    def test_pagination_follows_next_link(self):
        html = load_fixture("quotes_listing.html")
        assert quotes_find_next_page(html, QUOTES_LISTING_URL) == (
            "https://quotes.toscrape.com/page/2/"
        )

    def test_last_page_has_no_next_link(self):
        html = "<ul class='pager'></ul>"
        assert quotes_find_next_page(html, QUOTES_LISTING_URL) is None
