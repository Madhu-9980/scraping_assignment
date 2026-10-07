"""Central configuration for the multi-source scraping pipeline.

All tunable values live here so behaviour can be changed without touching
scraper/processing code.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"

FINAL_DATASET_CSV = OUTPUT_DIR / "final_dataset.csv"
SUMMARY_REPORT_JSON = OUTPUT_DIR / "summary_report.json"
REJECTED_RECORDS_JSON = OUTPUT_DIR / "rejected_records.json"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
BOOKS_SOURCE = "Books to Scrape"
QUOTES_SOURCE = "Quotes to Scrape"

KNOWN_SOURCES = (BOOKS_SOURCE, QUOTES_SOURCE)

BOOKS_BASE_URL = "https://books.toscrape.com/"
BOOKS_LISTING_URL = BOOKS_BASE_URL  # catalogue starts at the index page
QUOTES_BASE_URL = "https://quotes.toscrape.com/"
QUOTES_LISTING_URL = QUOTES_BASE_URL

# ---------------------------------------------------------------------------
# HTTP behaviour
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 10            # seconds, per request
MAX_RETRIES = 3                 # attempts after the first try fail
BACKOFF_BASE_DELAY = 0.5        # seconds; 0.5 -> 1.0 -> 2.0 exponential backoff
REQUEST_DELAY = 0.15            # polite minimum interval between requests
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 "
    "EducationalScraper/1.0 (+web-scraping-assignment)"
)

# Safety caps so a broken "next" link can never cause an infinite loop.
MAX_PAGES_PER_SOURCE = 60       # books: 50 real pages, quotes: 10 real pages
MAX_BOOK_DETAIL_PAGES = 1000    # matches the 1000 listing records

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "source",
    "source_url",
    "name_or_title",
    "category",
    "price",
    "rating",
    "author",
    "tags",
    "description",
    "scraped_at",
]

# Rating is stored as an int 1-5. The books site encodes it as a CSS class word.
RATING_WORD_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def ensure_directories() -> None:
    """Create output/log directories if they do not exist yet."""
    for directory in (OUTPUT_DIR, LOG_DIR):
        os.makedirs(directory, exist_ok=True)
