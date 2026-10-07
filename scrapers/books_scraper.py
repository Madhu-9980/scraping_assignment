"""Books to Scrape scraper (https://books.toscrape.com/).

Two phases:
1. **Listing pagination** – walks ``index.html``, ``catalogue/page-2.html``, ...
   via the ``li.next > a`` link (never hard-coded) and extracts the core fields
   available on the grid: title, URL, price, star rating, availability.
2. **Detail enrichment** – the listing page does *not* expose category or
   description, so each product page is fetched (throttled) to read the
   breadcrumb category and the product description. A failed detail fetch only
   leaves those two fields empty for that book; the record is kept.

Parsing is kept in pure functions (no network) so tests can run offline
against saved HTML fixtures.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from scrapers.base import FetchError, HttpFetcher

logger = logging.getLogger("scraper.books")


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O) – unit tested against fixtures
# ---------------------------------------------------------------------------
def parse_listing_page(html: str, page_url: str) -> list[dict]:
    """Parse one catalogue listing page into raw book records."""
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    for pod in soup.select("article.product_pod"):
        try:
            link = pod.select_one("h3 a")
            if link is None:
                logger.warning("Skipping product without a title link on %s", page_url)
                continue

            # The anchor text is truncated ("A Light in the ..."); the full
            # title lives in the title attribute.
            title = (link.get("title") or link.get_text(" ", strip=True)).strip()
            raw_url = link.get("href") or ""
            source_url = normalize_source_url(raw_url, page_url)

            price_el = pod.select_one("p.price_color")
            price_text = price_el.get_text(strip=True) if price_el else ""

            rating_el = pod.select_one("p.star-rating")
            rating_word = ""
            if rating_el is not None:
                classes = [c for c in (rating_el.get("class") or []) if c != "star-rating"]
                rating_word = classes[0] if classes else ""

            availability_el = pod.select_one("p.instock.availability")
            availability = (
                availability_el.get_text(" ", strip=True) if availability_el else ""
            )

            records.append(
                {
                    "source": config.BOOKS_SOURCE,
                    "source_url": source_url,
                    "name_or_title": title,
                    "category": None,        # only on the detail page
                    "price": price_text,
                    "rating": rating_word,   # e.g. "Three"; cleaned later
                    "author": None,          # not applicable for books
                    "tags": None,            # not applicable for books
                    "description": None,     # only on the detail page
                    "availability": availability,
                    "listing_page_url": page_url,
                }
            )
        except Exception as exc:  # defensive: never lose a whole page
            logger.warning("Failed to parse a product on %s: %s", page_url, exc)

    return records


def find_next_page(html: str, page_url: str) -> Optional[str]:
    """Return the absolute URL of the ``Next`` pagination link, if present."""
    soup = BeautifulSoup(html, "lxml")
    next_link = soup.select_one("li.next > a")
    if next_link is None or not next_link.get("href"):
        return None
    return urljoin(page_url, next_link["href"].strip())


def parse_detail_page(html: str, page_url: str) -> dict:
    """Extract ``category`` and ``description`` from a product page."""
    soup = BeautifulSoup(html, "lxml")
    category: Optional[str] = None
    description: Optional[str] = None

    # Category = last non-active breadcrumb entry that is not "Home".
    breadcrumb = soup.select_one("ul.breadcrumb")
    if breadcrumb is not None:
        crumbs = []
        for li in breadcrumb.select("li"):
            if "active" in (li.get("class") or []):
                continue
            text = li.get_text(" ", strip=True)
            if text and text.lower() != "home":
                crumbs.append(text)
        if crumbs:
            category = crumbs[-1]

    # Description = <p> immediately after the #product_description header div.
    desc_header = soup.select_one("#product_description")
    if desc_header is not None:
        desc_p = desc_header.find_next_sibling("p")
        if desc_p is not None:
            description = desc_p.get_text(" ", strip=True)

    return {"category": category, "description": description, "detail_url": page_url}


def normalize_source_url(href: str, base_url: str) -> str:
    """Join a relative catalogue href against its page URL and drop fragments."""
    absolute = urljoin(base_url, href.strip())
    return absolute.split("#", 1)[0]


# ---------------------------------------------------------------------------
# Networked scraping
# ---------------------------------------------------------------------------
def scrape_books(
    fetcher: HttpFetcher,
    max_pages: Optional[int] = config.MAX_PAGES_PER_SOURCE,
    enrich: bool = True,
    max_detail_pages: int = config.MAX_BOOK_DETAIL_PAGES,
) -> tuple[list[dict], list[dict]]:
    """Scrape Books to Scrape.

    Returns ``(records, errors)`` where *errors* is a list of
    ``{"source", "url", "stage", "error"}`` dicts for the summary report.
    """
    records: list[dict] = []
    errors: list[dict] = []

    page_url: Optional[str] = config.BOOKS_LISTING_URL
    page_number = 0

    # ---- phase 1: listing pages -----------------------------------------
    while page_url:
        page_number += 1
        if max_pages is not None and page_number > max_pages:
            logger.info("Books: reached max page cap (%s), stopping", max_pages)
            break

        try:
            html = fetcher.get(page_url)
        except FetchError as exc:
            logger.error("Books listing page failed (%s): %s", page_url, exc.reason)
            errors.append(
                {
                    "source": config.BOOKS_SOURCE,
                    "url": page_url,
                    "stage": "listing",
                    "error": exc.reason,
                }
            )
            break  # pagination is sequential; a broken page ends this source

        page_records = parse_listing_page(html, page_url)
        if not page_records:
            logger.warning("Books: no records found on %s (page %s)", page_url, page_number)
            errors.append(
                {
                    "source": config.BOOKS_SOURCE,
                    "url": page_url,
                    "stage": "listing",
                    "error": "no records parsed (unexpected markup)",
                }
            )

        records.extend(page_records)
        logger.info(
            "Books: page %s -> %s records (total %s)",
            page_number,
            len(page_records),
            len(records),
        )

        try:
            page_url = find_next_page(html, page_url)
        except Exception as exc:  # malformed markup must not crash pagination
            logger.warning("Books: could not read pagination on %s: %s", page_url, exc)
            page_url = None

    # ---- phase 2: detail enrichment (category + description) -------------
    if enrich and records:
        logger.info("Books: enriching %s detail pages (throttled) ...", len(records))
        for index, record in enumerate(records, start=1):
            detail_url = record.get("source_url")
            if not detail_url or index > max_detail_pages:
                continue
            try:
                html = fetcher.get(detail_url)
                details = parse_detail_page(html, detail_url)
                record["category"] = details["category"]
                record["description"] = details["description"]
            except FetchError as exc:
                # Keep the record; only the two optional fields stay empty.
                logger.warning(
                    "Books: detail fetch failed for %s: %s", detail_url, exc.reason
                )
                errors.append(
                    {
                        "source": config.BOOKS_SOURCE,
                        "url": detail_url,
                        "stage": "detail",
                        "error": exc.reason,
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Books: unexpected error parsing %s: %s", detail_url, exc
                )
                errors.append(
                    {
                        "source": config.BOOKS_SOURCE,
                        "url": detail_url,
                        "stage": "detail",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

            if index % 100 == 0:
                logger.info("Books: enriched %s/%s detail pages", index, len(records))

    return records, errors
