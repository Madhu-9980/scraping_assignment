"""Duplicate detection and removal.

Strategy
--------
A duplicate key is built from:

    ``source`` + normalized ``name_or_title`` (the only stable identity field
    that exists for *both* sources – book title / quote text).

Normalization rules applied to the key (in order):

1. Unicode NFKC normalization (folds full-width and compatibility forms);
2. Unicode casefolding (``casefold`` – stronger than ``lower``);
3. curly quotes and apostrophes (``‘ ’ “ ” '``) folded to nothing;
4. all punctuation/symbols replaced by spaces;
5. whitespace collapsed and the result stripped.

So ``" Example Book Title "``, ``"EXAMPLE BOOK TITLE"`` and
``"example   book title"`` all produce ``"example book title"``.

Consequences of scoping the key by ``source``: a book and a quote with the
same text are *not* duplicates of each other (they are different entities from
different websites).

The **first** occurrence is kept; later duplicates are removed from the final
dataset and reported (counts + a small sample) in ``summary_report.json``.
Removing them keeps the deliverable clean while the counts and the unit tests
prove the detection logic ran. Removal behaviour is documented in README.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger("dedup")

# Curly/typographic quotes and apostrophes folded away before comparison.
_QUOTE_CHARS = str.maketrans("", "", "‘’“”'`´’‛")

# Punctuation/symbols -> space (kept letters, digits, underscores).
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_for_dedup(value: Optional[str]) -> str:
    """Normalize a title/quote text into its canonical duplicate key form."""
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = text.casefold()
    text = text.translate(_QUOTE_CHARS)
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def dedup_key(record: dict) -> str:
    """Build the duplicate-detection key for one record."""
    source = (record.get("source") or "").strip().casefold()
    title = normalize_for_dedup(record.get("name_or_title"))
    return f"{source}::{title}"


def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove duplicate records, keeping the first occurrence.

    Returns ``(unique_records, dropped_records)``.
    ``dropped_records`` each carry a ``duplicate_of`` reference so the summary
    can show what was removed and which record it duplicated.
    """
    seen: dict[str, dict] = {}
    unique: list[dict] = []
    dropped: list[dict] = []

    for record in records:
        key = dedup_key(record)

        # Records with an empty key (should already be rejected by validation)
        # are never treated as duplicates of each other.
        if key.endswith("::") or not key.split("::", 1)[1]:
            unique.append(record)
            continue

        if key in seen:
            original = seen[key]
            dropped.append(
                {
                    "source": record.get("source"),
                    "source_url": record.get("source_url"),
                    "name_or_title": record.get("name_or_title"),
                    "duplicate_of": original.get("source_url"),
                    "normalized_key": key,
                }
            )
        else:
            seen[key] = record
            unique.append(record)

    if dropped:
        logger.info(
            "Deduplication: removed %s duplicate record(s)", len(dropped)
        )
    else:
        logger.info("Deduplication: no duplicates found")

    return unique, dropped
