# AI Usage Statement

This project was completed with AI assistance, as explicitly permitted by the
assignment brief (section 10). The candidate remains responsible for the final
implementation: every AI-generated line was reviewed, tested, and corrected.

## 1. AI tools used

| Tool                              | Version / context                             |
| --------------------------------- | ---------------------------------------------- |
| **Claude (OpenCode coding agent)** | Primary assistant for code, docs and debugging |

## 2. What the AI was used for

* **Understanding page structure** — inspecting the live HTML of both practice
  sites and identifying the correct selectors (title `title` attribute, rating
  CSS class word, breadcrumb category, `li.next > a` pagination).
* **Designing the data model** — the shared 10-field schema and how fields
  that don't apply to a source are represented.
* **Generating initial code** — module layout (`scrapers/`, `processing/`),
  the cleaning/validation/deduplication functions, and the orchestrator.
* **Designing tests** — fixture-based parsing tests plus unit tests for
  cleaning, validation and deduplication.
* **Documentation** — README structure and wording (reviewed and edited by
  hand against the actual implementation).
* **Debugging** — reviewing output when a test failed or a selector misbehaved.

## 3. Representative prompts

1. *"Build a Python web scraping pipeline for books.toscrape.com and
   quotes.toscrape.com: pagination, a common schema, cleaning, validation,
   dedup, CSV + JSON summary, logging and tests. Sites are static — choose the
   simplest appropriate library and justify it."*
2. *"The books listing page doesn't contain category or description. Propose
   options (detail-page fetch vs listing-only) with trade-offs, then implement
   the recommended one with throttling."*
3. *"How should duplicate detection work so that `" Example Book Title "`,
   `"EXAMPLE BOOK TITLE"` and `"example   book title"` collapse to one key, but
   a book and a quote with the same text don't?"*
4. *"Review `books_scraper.py` against the real HTML — are the selectors
   right?"* (this is how the `classes` vs `class` bug was found)
5. *"One test fails: `normalize_url("catalogue/…", ".../page-2.html")` gives
   `/catalogue/catalogue/…`. Is the code wrong or the test?"* (fetching the
   real `page-2.html` showed the test's href was unrealistic — the code's
   `urljoin` behaviour was correct.)

## 4. Parts of the code that were AI-assisted

Essentially all files started as AI-generated drafts: `config.py`,
`scrapers/base.py` (retry/backoff/rate limiting), both scrapers, all three
`processing/` modules, `main.py`, the test suite, fixtures, `requirements.txt`
and both documentation files. The candidate's review pass then verified
selectors against the live sites, ran the tests, and corrected issues.

## 5. Important changes made after reviewing AI output

1. **BeautifulSoup class-attribute bug (real bug, would have broken output).**
   The AI draft used `rating_el.get("classes", [])` and
   `li.get("classes", [])`. BeautifulSoup stores classes under the key
   `"class"` (a list), so `get("classes")` always returned `[]` — ratings would
   have been empty and the breadcrumb "active" filter would never have fired
   (category would have become the book *title* instead of "Poetry"). Fixed to
   `get("class") or []` in `scrapers/books_scraper.py`, and the fixture tests
   now cover both cases.
2. **Broken helper removed.** An early `clean_records()` draft contained an
   incomplete exception handler; rewritten to isolate per-record failures and
   log them (also made `cleaning.py` import `logging`).
3. **Wrong test expectation corrected (not a code bug).** A `normalize_url`
   test assumed index-style hrefs (`catalogue/…`) relative to `page-2.html`.
   Fetching the real `https://books.toscrape.com/catalogue/page-2.html` showed
   its hrefs are `in-her-wake_980/index.html` (relative to `/catalogue/`), so
   `urljoin` behaved correctly and the test was rewritten to match reality —
   plus an extra case for index-page hrefs.
4. **Defensive pagination.** `find_next_page` calls are wrapped so malformed
   markup logs a warning and stops that source instead of crashing the run.
5. **CSV float rendering** was adjusted so `51.7` doesn't become
   `51.700000000000003`-style artefacts in the deliverable.

## 6. Incorrect or incomplete AI suggestions discovered

* The `classes`/`class` BeautifulSoup mistake above (the most consequential
  one — silently wrong data, no crash).
* The unrealistic URL-joining test case described in §5.3.
* An initial suggestion to fetch detail pages for *every* book without a delay;
  replaced with a throttled, capped enrichment phase (`REQUEST_DELAY`,
  `MAX_BOOK_DETAIL_PAGES`) to respect the "reasonable request rates" rule.

No AI suggestion to bypass authentication, CAPTCHAs, robots restrictions or
other controls was accepted — the assignment restricts scraping to the two
public practice sites, which is exactly what the pipeline does.

## 7. How the final solution was tested and verified

1. **Unit tests:** `python -m pytest tests/ -v` → **96 passed** (offline; the
   parser tests run against saved HTML fixtures, so they also pin the expected
   selector behaviour against future edits).
2. **Smoke run:** `python main.py --max-pages 2 --skip-details` → exit code 0,
   60 records, outputs written, log created.
3. **Full run:** `python main.py` → ~1,100 requests, expected totals
   (1,000 books + 100 quotes), 0 validation rejects, 0 duplicates (the sites
   are de-duplicated sandboxes — dedup correctness is proven by unit tests),
   execution time recorded in `summary_report.json`.
4. **Manual spot checks:** sampled rows from `final_dataset.csv` compared
   against the live pages (title, price, rating, category, description, URL
   resolution from `page-2.html`); quote text/tags/author verified against
   `quotes.toscrape.com`.
5. **Log review:** `logs/pipeline.log` inspected for `ERROR`/`WARNING` entries
   beyond expected diagnostics; `summary_report.json` checked for
   `page_errors: []`.
