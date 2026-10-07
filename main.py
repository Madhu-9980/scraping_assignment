#!/usr/bin/env python3
"""Multi-source web scraping & data consolidation pipeline.

Workflow
--------
Website A ─┐
Website B ─┼─> Scraping ─> Cleaning ─> Validation ─> Deduplication ─> Consolidation
           ┘

Usage
-----
    python main.py                 # full run (all pages + book detail pages)
    python main.py --skip-details  # listing pages only (fast smoke test)
    python main.py --max-pages 2   # limit pagination per source (quick test)
    python main.py --delay 0.3     # slower, politer request rate

Outputs (in ``output/``):
    final_dataset.csv       consolidated standardised dataset
    summary_report.json     metrics: collected / cleaned / rejected / duplicates
    rejected_records.json   records that failed validation, with reasons
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time

import config
from processing.cleaning import clean_records
from processing.deduplication import deduplicate
from processing.validation import rejection_reason_counts, validate_records
from scrapers.base import HttpFetcher, setup_logging
from scrapers.books_scraper import scrape_books
from scrapers.quotes_scraper import scrape_quotes

logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _csv_value(value) -> str:
    """Render a value for CSV (None -> empty string, floats without noise)."""
    if value is None:
        return ""
    if isinstance(value, float):
        # Avoid "51.770000000000003" style artefacts while keeping ints clean.
        return f"{value:.2f}" if value % 1 else str(int(value))
    return str(value)


def write_csv(records: list[dict], path=config.FINAL_DATASET_CSV) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=config.CSV_COLUMNS,
            extrasaction="ignore",
            restval="",
        )
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record.get(column)) for column in config.CSV_COLUMNS})
    logger.info("Wrote %s records to %s", len(records), path)


def write_json(payload, path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    logger.info("Wrote %s", path)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def scrape_source(source: str, fetcher: HttpFetcher, args) -> tuple[list[dict], list[dict]]:
    """Run one source's scraper; a total source failure returns ([], [error])."""
    try:
        if source == config.BOOKS_SOURCE:
            return scrape_books(
                fetcher,
                max_pages=args.max_pages,
                enrich=not args.skip_details,
            )
        if source == config.QUOTES_SOURCE:
            return scrape_quotes(fetcher, max_pages=args.max_pages)
        raise ValueError(f"Unknown source: {source}")
    except Exception as exc:  # one broken source must not stop the other
        logger.exception("Source %s failed completely: %s", source, exc)
        return [], [
            {
                "source": source,
                "url": "",
                "stage": "source",
                "error": f"{type(exc).__name__}: {exc}",
            }
        ]


def run_pipeline(args) -> dict:
    started = time.perf_counter()
    setup_logging(getattr(logging, args.log_level.upper(), logging.INFO))
    config.ensure_directories()

    logger.info("=" * 70)
    logger.info("Pipeline started | sources=%s", ", ".join(config.KNOWN_SOURCES))
    logger.info(
        "Settings: delay=%.2fs timeout=%ss retries=%s max_pages=%s enrich_details=%s",
        args.delay,
        config.REQUEST_TIMEOUT,
        config.MAX_RETRIES,
        args.max_pages,
        not args.skip_details,
    )

    # -- 1. Scrape ---------------------------------------------------------
    raw_records: list[dict] = []
    collected_per_source: dict[str, int] = {}
    page_errors: list[dict] = []

    with HttpFetcher(delay=args.delay) as fetcher:
        for source in config.KNOWN_SOURCES:
            records, errors = scrape_source(source, fetcher, args)
            raw_records.extend(records)
            collected_per_source[source] = len(records)
            page_errors.extend(errors)
            logger.info(
                "Source '%s': %s record(s), %s error(s)",
                source,
                len(records),
                len(errors),
            )

    logger.info("Total raw records collected: %s", len(raw_records))

    # -- 2. Clean ----------------------------------------------------------
    cleaned_records = clean_records(raw_records, logger=logging.getLogger("cleaning"))
    logger.info("Records after cleaning: %s", len(cleaned_records))

    # -- 3. Validate -------------------------------------------------------
    valid_records, rejected_records = validate_records(cleaned_records)
    reasons_breakdown = rejection_reason_counts(rejected_records)

    # -- 4. Deduplicate ----------------------------------------------------
    unique_records, dropped_duplicates = deduplicate(valid_records)

    # -- 5. Consolidate & write -------------------------------------------
    write_csv(unique_records)

    rejected_payload = [
        {
            "reasons": entry["reasons"],
            "source": entry["record"].get("source"),
            "source_url": entry["record"].get("source_url"),
            "name_or_title": entry["record"].get("name_or_title"),
            "record": {
                key: entry["record"].get(key) for key in config.CSV_COLUMNS
            },
        }
        for entry in rejected_records
    ]
    write_json(rejected_payload, config.REJECTED_RECORDS_JSON)

    execution_time = round(time.perf_counter() - started, 2)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": list(config.KNOWN_SOURCES),
        "records_collected_per_source": collected_per_source,
        "total_records_collected": len(raw_records),
        "total_records_after_cleaning": len(cleaned_records),
        "records_rejected_during_validation": len(rejected_records),
        "rejection_reasons_breakdown": reasons_breakdown,
        "duplicate_records_detected": len(dropped_duplicates),
        "duplicate_records_removed": len(dropped_duplicates),
        "duplicate_sample": dropped_duplicates[:10],
        "final_record_count": len(unique_records),
        "page_errors": page_errors,
        "page_error_count": len(page_errors),
        "execution_time_seconds": execution_time,
        "settings": {
            "request_delay_seconds": args.delay,
            "request_timeout_seconds": config.REQUEST_TIMEOUT,
            "max_retries": config.MAX_RETRIES,
            "max_pages_per_source": args.max_pages,
            "detail_enrichment": not args.skip_details,
        },
        "outputs": {
            "final_dataset": str(config.FINAL_DATASET_CSV.name),
            "rejected_records": str(config.REJECTED_RECORDS_JSON.name),
            "log_file": str(config.LOG_FILE.name),
        },
    }
    write_json(summary, config.SUMMARY_REPORT_JSON)

    logger.info("-" * 70)
    logger.info("Collected per source : %s", collected_per_source)
    logger.info("After cleaning       : %s", len(cleaned_records))
    logger.info("Rejected (validation): %s", len(rejected_records))
    logger.info("Duplicates removed   : %s", len(dropped_duplicates))
    logger.info("Final record count   : %s", len(unique_records))
    logger.info("Page-level errors    : %s", len(page_errors))
    logger.info("Execution time       : %.2fs", execution_time)
    logger.info("Outputs written to   : %s", config.OUTPUT_DIR)
    logger.info("=" * 70)

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Books to Scrape and Quotes to Scrape into one dataset."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=config.MAX_PAGES_PER_SOURCE,
        help="Safety cap on pages fetched per source (default: %(default)s).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.REQUEST_DELAY,
        help="Minimum delay in seconds between requests (default: %(default)s).",
    )
    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Skip book detail-page enrichment (category/description) for a fast run.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        run_pipeline(args)
        return 0
    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        return 130
    except Exception:
        logging.getLogger("pipeline").exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
