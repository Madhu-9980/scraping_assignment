"""Quotes to Scrape scraper (https://quotes.toscrape.com/).

Paginates by following the ``li.next > a`` ("Next →") link until it disappears;
page URLs are never hard-coded. Parsing lives in pure functions so tests can
run offline against saved HTML fixtures.

Field mapping into the shared schema:
* quote text            -> name_or_title
* author                -> author
* tags                  -> tags (list, joined later for CSV)
* quote page URL        -> source_url
* price/rating/category -> None (not applicable to this source)
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from scrapers.base import FetchError, HttpFetcher

logger = logging.getLogger("scraper.quotes")


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O) – unit tested against fixtures
# ---------------------------------------------------------------------------
def parse_quotes_page(html: str, page_url: str) -> list[dict]:
    """Parse one quotes listing page into raw record dicts."""
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    for quote in soup.select("div.quote"):
        try:
            text_el = quote.select_one("span.text")
            author_el = quote.select_one("small.author")

            text = text_el.get_text(" ", strip=True) if text_el else ""
            author = author_el.get_text(strip=True) if author_el else ""

            author_link = quote.select_one('a[href^="/author/"]')
            author_url = ""
            if author_link is not None and author_link.get("href"):
                author_url = urljoin(page_url, author_link["href"].strip())

            tags = [a.get_text(strip=True) for a in quote.select("div.tags a.tag")]

            records.append(
                {
                    "source": config.QUOTES_SOURCE,
                    "source_url": page_url,
                    "name_or_title": text,
                    "category": None,       # not applicable to quotes
                    "price": None,          # not applicable to quotes
                    "rating": None,         # not applicable to quotes
                    "author": author,
                    "author_url": author_url,
                    "tags": tags,
                    "description": None,    # not applicable to quotes
                }
            )
        except Exception as exc:  # defensive: never lose a whole page
            logger.warning("Failed to parse a quote on %s: %s", page_url, exc)

    return records


def find_next_page(html: str, page_url: str) -> Optional[str]:
    """Return the absolute URL of the ``Next`` pagination link, if present."""
    soup = BeautifulSoup(html, "lxml")
    next_link = soup.select_one("li.next > a")
    if next_link is None or not next_link.get("href"):
        return None
    return urljoin(page_url, next_link["href"].strip())


# ---------------------------------------------------------------------------
# Networked scraping
# ---------------------------------------------------------------------------
def scrape_quotes(
    fetcher: HttpFetcher,
    max_pages: Optional[int] = config.MAX_PAGES_PER_SOURCE,
) -> tuple[list[dict], list[dict]]:
    """Scrape Quotes to Scrape.

    Returns ``(records, errors)``.
    """
    records: list[dict] = []
    errors: list[dict] = []

    page_url: Optional[str] = config.QUOTES_LISTING_URL
    page_number = 0

    while page_url:
        page_number += 1
        if max_pages is not None and page_number > max_pages:
            logger.info("Quotes: reached max page cap (%s), stopping", max_pages)
            break

        try:
            html = fetcher.get(page_url)
        except FetchError as exc:
            logger.error("Quotes page failed (%s): %s", page_url, exc.reason)
            errors.append(
                {
                    "source": config.QUOTES_SOURCE,
                    "url": page_url,
                    "stage": "listing",
                    "error": exc.reason,
                }
            )
            break  # sequential pagination: stop this source, keep the rest

        page_records = parse_quotes_page(html, page_url)
        if not page_records:
            logger.warning(
                "Quotes: no records found on %s (page %s)", page_url, page_number
            )
            errors.append(
                {
                    "source": config.QUOTES_SOURCE,
                    "url": page_url,
                    "stage": "listing",
                    "error": "no records parsed (unexpected markup)",
                }
            )

        records.extend(page_records)
        logger.info(
            "Quotes: page %s -> %s records (total %s)",
            page_number,
            len(page_records),
            len(records),
        )

        try:
            page_url = find_next_page(html, page_url)
        except Exception as exc:
            logger.warning("Quotes: could not read pagination on %s: %s", page_url, exc)
            page_url = None

    return records, errors
