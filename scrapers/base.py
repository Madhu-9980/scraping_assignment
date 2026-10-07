"""Shared HTTP layer used by every source scraper.

Provides:
* a ``requests.Session`` with a sensible User-Agent,
* per-request timeout,
* exponential-backoff retries for transient failures (network errors, 429/5xx),
* a polite minimum delay between requests (rate limiting),
* structured logging to console and ``logs/pipeline.log``.

A page-level failure raises :class:`FetchError` *after* retries are exhausted;
scraper code catches it and moves on so one bad page never kills the run.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Optional

import requests

import config

logger = logging.getLogger("scraper.http")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging: console + rotating-free file handler."""
    config.ensure_directories()

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when called more than once (e.g. in tests).
    if root.handlers:
        return

    formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


class FetchError(Exception):
    """Raised when a URL cannot be fetched after all retry attempts."""

    def __init__(self, url: str, reason: str, status_code: Optional[int] = None):
        self.url = url
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"Failed to fetch {url}: {reason}")


class HttpFetcher:
    """Rate-limited, retrying HTTP GET client."""

    def __init__(
        self,
        timeout: float = config.REQUEST_TIMEOUT,
        max_retries: int = config.MAX_RETRIES,
        backoff_base: float = config.BACKOFF_BASE_DELAY,
        delay: float = config.REQUEST_DELAY,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.delay = delay
        self._last_request_at = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.USER_AGENT})

    # -- internal helpers ---------------------------------------------------
    def _throttle(self) -> None:
        """Enforce a minimum interval between consecutive requests."""
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    @staticmethod
    def _is_retryable(exc: Exception, status_code: Optional[int]) -> bool:
        if status_code in config.RETRYABLE_STATUS_CODES:
            return True
        return isinstance(
            exc,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ),
        )

    # -- public API ---------------------------------------------------------
    def get(self, url: str) -> str:
        """GET *url* and return the response text.

        Retries transient failures with exponential backoff
        (``backoff_base * 2**attempt``). Raises :class:`FetchError` when the
        URL ultimately cannot be retrieved.
        """
        last_reason = "unknown error"
        last_status: Optional[int] = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                wait = self.backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Retry %s/%s for %s in %.1fs (%s)",
                    attempt,
                    self.max_retries,
                    url,
                    wait,
                    last_reason,
                )
                time.sleep(wait)

            self._throttle()
            try:
                self._last_request_at = time.monotonic()
                response = self._session.get(url, timeout=self.timeout)
                last_status = response.status_code

                if response.status_code == 200:
                    logger.debug("Fetched %s (%s bytes)", url, len(response.content))
                    return response.text

                last_reason = f"HTTP {response.status_code}"
                # 4xx other than 429 are permanent -> do not retry.
                if response.status_code not in config.RETRYABLE_STATUS_CODES:
                    logger.error("Non-retryable status %s for %s", response.status_code, url)
                    raise FetchError(url, last_reason, status_code=response.status_code)

            except requests.exceptions.RequestException as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
                if not self._is_retryable(exc, last_status):
                    logger.error("Non-retryable request error for %s: %s", url, last_reason)
                    raise FetchError(url, last_reason) from exc

        logger.error("Giving up on %s after %s attempts", url, self.max_retries + 1)
        raise FetchError(url, last_reason, status_code=last_status)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpFetcher":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
