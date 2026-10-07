"""Record validation performed *after* cleaning and *before* deduplication.

Every record is checked against the rules that apply to its source. Invalid
records are never written to the final dataset – they are collected together
with machine-readable reasons and exported to ``output/rejected_records.json``
so reviewers can see exactly what was rejected and why.

Rules
-----
Common
    * ``source`` must be one of the known sources,
    * ``name_or_title`` must be present,
    * ``source_url`` must be a valid-looking http(s) URL,
    * ``scraped_at`` must be present.
Books to Scrape
    * ``price`` must be numeric and > 0,
    * ``rating`` must be an integer within 1-5.
Quotes to Scrape
    * ``author`` must be present.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import config

logger = logging.getLogger("validation")


def _is_valid_url(value: Any) -> bool:
    if not value or not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_record(record: dict) -> list[str]:
    """Return a list of rule-violation reasons (empty list == valid)."""
    reasons: list[str] = []

    source = record.get("source")
    if source not in config.KNOWN_SOURCES:
        reasons.append(f"unknown_source: {source!r}")

    if not record.get("name_or_title"):
        reasons.append("missing_name_or_title")

    if not _is_valid_url(record.get("source_url")):
        reasons.append(f"invalid_source_url: {record.get('source_url')!r}")

    if not record.get("scraped_at"):
        reasons.append("missing_scraped_at")

    # -- source-specific rules --------------------------------------------
    if source == config.BOOKS_SOURCE:
        price = record.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            reasons.append(f"price_not_numeric: {price!r}")
        elif price <= 0:
            reasons.append(f"price_not_positive: {price!r}")

        rating = record.get("rating")
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
            reasons.append(f"rating_out_of_range: {rating!r}")

    elif source == config.QUOTES_SOURCE:
        if not record.get("author"):
            reasons.append("missing_author")

    return reasons


def validate_records(
    records: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Split records into ``(valid, rejected)``.

    Each rejected entry is ``{"record": ..., "reasons": [...]}``.
    """
    valid: list[dict] = []
    rejected: list[dict] = []

    for record in records:
        reasons = validate_record(record)
        if reasons:
            rejected.append({"record": record, "reasons": reasons})
            logger.warning(
                "Rejected record from %s (%s): %s",
                record.get("source"),
                record.get("source_url"),
                "; ".join(reasons),
            )
        else:
            valid.append(record)

    logger.info(
        "Validation: %s passed, %s rejected", len(valid), len(rejected)
    )
    return valid, rejected


def rejection_reason_counts(rejected: list[dict]) -> dict[str, int]:
    """Aggregate rejection reasons for the summary report."""
    counts: dict[str, int] = {}
    for entry in rejected:
        for reason in entry.get("reasons", []):
            # Strip the value part: "invalid_source_url: 'x'" -> "invalid_source_url"
            key = reason.split(":", 1)[0].strip()
            counts[key] = counts.get(key, 0) + 1
    return counts
