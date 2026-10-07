"""Pure data-cleaning and standardisation functions.

No I/O here – every function takes a value (or record) and returns a cleaned
value, which makes the whole layer trivially unit-testable.

Conventions:
* missing values become ``None`` (JSON) / empty string (CSV), never invented;
* prices become ``float``; ratings become ``int`` 1-5;
* text is Unicode-normalised (NFKC) and internal whitespace is collapsed;
* URLs are absolutised against their base and validated.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import config

# Matches numbers like 51.77 / 1,234.50 / 13 / -2.5
_NUMBER_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_WHITESPACE_RE = re.compile(r"\s+")
# Anything that is not a letter, digit or space (covers curly quotes/punctuation)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def clean_text(value: Any) -> Optional[str]:
    """Normalise a text value: NFKC, strip, collapse internal whitespace.

    Returns ``None`` for empty/missing input so nulls stay uniform.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\xa0", " ")  # non-breaking space seen on some pages
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def parse_price(value: Any) -> Optional[float]:
    """Convert ``"£51.77"`` / ``"$1,234.50"`` / ``51.77`` to ``51.77``.

    Returns ``None`` when no numeric value can be extracted.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    text = str(value).replace(",", "").strip()
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_rating(value: Any) -> Optional[int]:
    """Convert a rating to an ``int`` between 1 and 5.

    Accepts: ``3``, ``"3"``, ``"Three"``, ``"star-rating Three"``, ``"3/5"``.
    Returns ``None`` when the value is missing or out of range.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        rating = int(value)
        return rating if 1 <= rating <= 5 else None

    text = str(value).strip()
    if not text:
        return None

    # Plain digit ("3", "3/5")
    digit_match = re.search(r"\d", text)
    if digit_match and text.replace("/", "").replace(" ", "").isdigit():
        try:
            rating = int(text.split("/")[0])
            return rating if 1 <= rating <= 5 else None
        except ValueError:
            return None

    # Word form, possibly prefixed with the CSS class ("star-rating Three")
    for word in text.lower().split():
        if word in config.RATING_WORD_MAP:
            return config.RATING_WORD_MAP[word]
    return None


def normalize_url(url: Any, base: Optional[str] = None) -> Optional[str]:
    """Absolutise *url* against *base*, drop fragments, validate the result.

    Returns ``None`` when the URL is missing or has no http(s) scheme/host.
    """
    if url is None:
        return None
    text = str(url).strip()
    if not text:
        return None
    if base:
        text = urljoin(base, text)
    text = text.split("#", 1)[0]

    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return text


def parse_tags(value: Any) -> Optional[str]:
    """Normalise tags into a ``"; "``-joined string for CSV output."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = clean_text(value)
        return cleaned
    if isinstance(value, Iterable):
        tags = [t for t in (clean_text(v) for v in value) if t]
        return "; ".join(tags) if tags else None
    return clean_text(value)


def utc_timestamp() -> str:
    """Current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_record(record: dict) -> dict:
    """Apply every cleaning rule to one raw record.

    Unknown extra keys (e.g. ``availability``) are preserved untouched.
    """
    cleaned = dict(record)

    cleaned["source"] = clean_text(record.get("source"))
    cleaned["name_or_title"] = clean_text(record.get("name_or_title"))
    cleaned["category"] = clean_text(record.get("category"))
    cleaned["author"] = clean_text(record.get("author"))
    cleaned["description"] = clean_text(record.get("description"))

    cleaned["price"] = parse_price(record.get("price"))
    cleaned["rating"] = parse_rating(record.get("rating"))

    base = record.get("listing_page_url") or config.BOOKS_BASE_URL
    cleaned["source_url"] = normalize_url(record.get("source_url"), base)
    cleaned["tags"] = parse_tags(record.get("tags"))

    # Never invent a timestamp – reuse the original one if the record was
    # cleaned twice.
    cleaned["scraped_at"] = record.get("scraped_at") or utc_timestamp()

    return cleaned


def clean_records(
    records: list[dict], logger: Optional[logging.Logger] = None
) -> list[dict]:
    """Clean every record, isolating per-record failures.

    A record whose cleaning blows up is skipped (and logged) instead of
    stopping the whole pipeline.
    """
    cleaned: list[dict] = []
    for index, record in enumerate(records):
        try:
            cleaned.append(clean_record(record))
        except Exception as exc:
            message = f"Cleaning failed for record #{index}: {type(exc).__name__}: {exc}"
            if logger is not None:
                logger.warning(message)
            else:
                logging.getLogger("cleaning").warning(message)
    return cleaned
