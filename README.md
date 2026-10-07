# Multi-Source Web Scraping & Data Consolidation

Python pipeline that scrapes two public practice websites — **Books to Scrape**
(https://books.toscrape.com/) and **Quotes to Scrape**
(https://quotes.toscrape.com/) — normalises their different structures into one
standardised schema, cleans and validates the data, removes duplicates, and
produces a single consolidated dataset plus a machine-readable summary report.

```
Website A ─┐
Website B ─┼─> Scraping ─> Cleaning ─> Validation ─> Deduplication ─> Consolidation
           ┘
```

---

## 1. Requirements

| Item    | Version                                   |
| ------- | ----------------------------------------- |
| Python  | **3.10 or newer** (developed & tested on 3.12.10) |
| OS      | Windows / macOS / Linux                   |

## 2. Installation

```bash
cd scraping_assignment
python -m venv .venv                # optional but recommended
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Dependencies:

| Package          | Purpose                                   |
| ---------------- | ----------------------------------------- |
| `requests`       | HTTP sessions, timeouts, retries          |
| `beautifulsoup4` | HTML parsing                              |
| `lxml`           | Fast, forgiving HTML parser for BeautifulSoup |
| `pytest`         | Test suite (dev only)                     |

## 3. How to run

```bash
python main.py                 # full run (all pages + book detail enrichment)
python main.py --skip-details  # listing pages only – fast smoke test (~10 s)
python main.py --max-pages 2   # limit pagination per source (quick test)
python main.py --delay 0.3     # slower, politer request rate
python main.py --log-level DEBUG
python main.py -h              # all options
```

Run the tests:

```bash
python -m pytest tests/ -v
```

A full run performs ~1,100 requests at a polite 0.15 s interval and finishes in
roughly **5–8 minutes**. Progress is printed to the console and written to
`logs/pipeline.log`.

## 4. Run on GitHub Actions

The `Run scraper` workflow runs the pipeline on every push to `main`, once a
week (Sunday at 03:00 UTC), and can also be started manually:

1. Push this repository to GitHub.
2. Open the repository's **Actions** tab and select **Run scraper**.
3. To start a run immediately, choose **Run workflow** and confirm.
4. When the run succeeds, open it and download the **scraping-results** artifact.

The artifact contains `final_dataset.csv`, `summary_report.json`, and
`rejected_records.json`. It is retained for 14 days. To keep hosted runs quick,
the workflow uses a 0.3-second request delay and skips book detail-page
enrichment, so book category and description fields are empty. Local runs of
`python main.py` still perform the full scrape by default. Generated files are
not committed to the repository.

The latest successful scrape is also published as a public website at
<https://madhu-9980.github.io/scraping_assignment/>.

## 5. Project structure

```
scraping_assignment/
├── scrapers/
│   ├── base.py              # HttpFetcher: session, timeout, retry+backoff, rate limit, logging
│   ├── books_scraper.py     # listing pagination + detail-page enrichment
│   └── quotes_scraper.py    # listing pagination
├── processing/
│   ├── cleaning.py          # pure transform functions (no I/O)
│   ├── validation.py        # per-source rules → rejects with reasons
│   └── deduplication.py     # normalized keys → drop duplicates, report stats
├── tests/
│   ├── fixtures/            # saved HTML samples (book list, book detail, quotes)
│   ├── test_cleaning.py
│   ├── test_validation.py
│   ├── test_deduplication.py
│   └── test_scrapers.py     # offline parsing tests (no network needed)
├── output/                  # final_dataset.csv, summary_report.json, rejected_records.json
├── logs/                    # pipeline.log
├── config.py                # URLs, delays, timeouts, schema, safety caps
├── main.py                  # CLI entry point / pipeline orchestrator
├── conftest.py              # puts project root on sys.path for pytest
├── requirements.txt
├── README.md
└── AI_USAGE.md
```

**Separation of concerns:** scrapers only *extract* raw values; `processing/`
only *transforms* them (pure functions, no I/O → easy to unit test); `main.py`
orchestrates and writes outputs.

## 6. How pagination works

Neither source's page URLs are hard-coded. Each scraper follows the site's
"Next" link until it disappears:

* **Books to Scrape** — `li.next > a` → `catalogue/page-2.html`, `page-3.html`, …
  (50 pages × 20 items = 1,000 books). Each next href is resolved with
  `urljoin()` against the current page URL, so relative links work anywhere in
  the catalogue.
* **Quotes to Scrape** — `li.next > a` → `/page/2/`, `/page/3/`, …
  (10 pages × 10 items = 100 quotes). The loop stops when no next link exists.

Safety: a `MAX_PAGES_PER_SOURCE` cap (60) guarantees that a broken "next" link
can never cause an infinite loop; `--max-pages` can lower it from the CLI.

## 7. Data model (standardised schema)

One row shape for both sources — `output/final_dataset.csv`:

| Column          | Books to Scrape                    | Quotes to Scrape                |
| --------------- | ---------------------------------- | ------------------------------- |
| `source`        | `"Books to Scrape"`                | `"Quotes to Scrape"`            |
| `source_url`    | product page URL (absolute)        | listing page URL of the quote   |
| `name_or_title` | full book title                    | quote text                      |
| `category`      | breadcrumb category (detail page)  | `""` (n/a)                      |
| `price`         | numeric `float` (currency removed) | `""` (n/a)                      |
| `rating`        | `int` 1–5                          | `""` (n/a)                      |
| `author`        | `""` (n/a)                         | author name                     |
| `tags`          | `""` (n/a)                         | `"; "`-joined tag list          |
| `description`   | product description (detail page)  | `""` (n/a)                      |
| `scraped_at`    | ISO-8601 UTC timestamp             | ISO-8601 UTC timestamp          |

Fields that do not apply to a source are left **empty/`null` — never
invented**. `None` is used in Python and rendered as an empty CSV cell.
An extra non-CSV field, `availability` ("In stock (22 available)"), is captured
for books in memory but not part of the required schema.

## 8. Source exploration notes (Step 1)

**Books to Scrape**

* Grid item: `article.product_pod`.
* Full title is in the `title` attribute of `h3 > a` — the visible anchor text
  is truncated (`A Light in the ...`).
* Price: `p.price_color` → `£51.77`; rating: CSS **class word** on
  `p.star-rating` (`Three` → 3); availability: `p.instock.availability`.
* Listing hrefs are **relative** and differ between pages
  (`catalogue/...` on the index, `in-her-wake_980/...` on `page-2`) → always
  resolved with `urljoin(current_page, href)`.
* **Category and description exist only on the detail page** (breadcrumb
  `ul.breadcrumb` and the `<p>` after `#product_description`), which is why a
  second, throttled enrichment phase fetches the ~1,000 product pages.

**Quotes to Scrape**

* Item: `div.quote`; text `span.text` (wrapped in typographic quotes
  `“…”`), author `small.author`, author link `a[href^="/author/"]`,
  tags `div.tags a.tag`.
* No price/rating/category → those columns stay empty.

## 9. Cleaning approach (`processing/cleaning.py`)

Pure functions, no I/O:

| Function        | Behaviour                                                                 |
| --------------- | ------------------------------------------------------------------------- |
| `clean_text`    | Unicode **NFKC** normalisation, non-breaking spaces → space, collapse runs of whitespace, strip; empty → `None` |
| `parse_price`   | strips currency symbols/commas (`£51.77` → `51.77`, `$1,234.50` → `1234.5`) → `float`; no number → `None` |
| `parse_rating`  | word (`"Three"`), class-prefixed (`"star-rating Four"`), digit (`"4"`, `"3/5"`) → `int 1–5`; out of range → `None` |
| `normalize_url` | `urljoin` against the page URL, fragments stripped, must be `http(s)` with a host → else `None` |
| `parse_tags`    | list → de-duplicated-order-preserving `"; "`-joined string; empty → `None` |
| `clean_record`  | applies all of the above and stamps `scraped_at` (ISO-8601 UTC)           |

A record that throws during cleaning is skipped and logged — the pipeline never
stops on one bad row.

## 10. Validation approach (`processing/validation.py`)

Runs after cleaning, before deduplication. `validate_record()` returns a list
of reasons (empty = valid):

* **Common:** `source` must be a known source; `name_or_title` present;
  `source_url` a well-formed `http(s)` URL; `scraped_at` present.
* **Books:** `price` numeric and `> 0`; `rating` an `int` within 1–5.
* **Quotes:** `author` present.

Rejected records are **not written to the final dataset**. They are exported to
`output/rejected_records.json` with their reasons, and a per-reason breakdown
appears in `summary_report.json` (`rejection_reasons_breakdown`).

## 11. Deduplication approach (`processing/deduplication.py`)

Duplicate key = **`source` + normalised `name_or_title`** (book title / quote
text) — the only stable identity field that exists for *both* sources.

Normalisation applied to the key, in order:

1. Unicode **NFKC** normalisation;
2. Unicode **`casefold()`** (stronger than `lower()`);
3. typographic quotes/apostrophes (`‘ ’ “ ” '`) folded away;
4. all punctuation/symbols replaced by spaces;
5. whitespace collapsed, then stripped.

So `" Example Book Title "`, `"EXAMPLE BOOK TITLE"` and `"example   book title"`
all collapse to the same key `example book title`, and
`“The world as we have created it.”` matches
`"The world as we have created it."`. Scoping the key by `source` means a book
and a quote with identical text are **not** treated as duplicates of each
other.

**Why remove rather than flag:** the final deliverable should be a clean
dataset; every removal is still fully measurable — `summary_report.json`
contains `duplicate_records_detected` / `duplicate_records_removed` plus a
`duplicate_sample` showing the dropped row and the record it duplicated
(`duplicate_of` → its `source_url`). The behaviour is also proven by unit tests
(`tests/test_deduplication.py`), which matters because the two practice sites
happen to contain few natural duplicates. First occurrence wins; the rest are
dropped.

## 12. Error handling & logging

* **Transport:** `HttpFetcher` (`scrapers/base.py`) wraps a `requests.Session`
  with a 10 s timeout and **3 retries with exponential backoff**
  (0.5 s → 1 s → 2 s) for connection errors, timeouts and retryable statuses
  (429/500/502/503/504). Other 4xx responses fail immediately (no pointless
  retries on 404).
* **Rate limiting:** a minimum 0.15 s interval between requests (`--delay`),
  plus a descriptive User-Agent — respectful traffic per the assignment rules.
* **Page level:** each page fetch/parse is wrapped in `try/except`. A failed
  book *detail* page only leaves `category`/`description` empty for that book;
  a failed listing page ends that source's pagination (pages are sequential)
  but **never** stops the other source.
* **Source level:** each source runs inside its own `try/except` — if one
  source dies entirely, the other still produces data.
* **Logging:** console **and** `logs/pipeline.log`, format
  `timestamp | LEVEL | module | message`. Every retry, parse skip, rejection
  and per-page record count is visible; page-level errors are also listed in
  `summary_report.json` (`page_errors`).
* **Exit codes:** `0` on success (even with partial page failures — they are
  reported in the summary), `1` on unexpected pipeline failure, `130` on
  Ctrl-C.

## 12. Output description

```
output/
├── final_dataset.csv        # consolidated standardised dataset
├── summary_report.json      # metrics (see below)
└── rejected_records.json    # validation rejects + reasons
logs/
└── pipeline.log             # full execution log (sample included in submission)
```

`summary_report.json` includes:

* `records_collected_per_source`, `total_records_collected`
* `total_records_after_cleaning`
* `records_rejected_during_validation` + `rejection_reasons_breakdown`
* `duplicate_records_detected` / `duplicate_records_removed` / `duplicate_sample`
* `final_record_count`
* `page_errors` (source, URL, stage, error) and `page_error_count`
* `execution_time_seconds` and the settings used

## 13. Testing

96 offline tests (`python -m pytest tests/ -v`):

* **Cleaning** — whitespace/NFKC, price parsing, rating parsing (words,
  classes, digits, out-of-range), URL joining/validation, tags, end-to-end
  record cleaning.
* **Validation** — every rejection rule and the reason-count aggregation.
* **Deduplication** — the exact whitespace/capitalisation variants from the
  brief, curly-quote folding, source scoping, first-occurrence-wins.
* **Scrapers** — parsing against saved HTML fixtures (no network): titles from
  `title` attributes, relative URL joining, rating class words, breadcrumb
  category, description extraction, tag lists, next-page discovery and
  termination.

## 14. Assumptions

* The two sites are static HTML — no JavaScript rendering is required, so
  Requests + BeautifulSoup is sufficient (Scrapy/Selenium/Playwright would add
  weight without benefit).
* `category`/`description` for books come from product detail pages; a failed
  detail fetch yields empty values rather than dropping the book.
* A quote's `source_url` is the listing page it appeared on (the site gives no
  per-quote permalink).
* Prices are cleaned of currency symbols; both sites currently use `£`, but
  the parser also handles `$`, `€` and thousands separators.
* `rating` is stored as an `int 1–5` (the site encodes it as a CSS class word).
* Rejected/duplicate records are excluded from `final_dataset.csv` but fully
  reported; the pipeline exits `0` when partial page failures occurred, since
  partial data is still valuable and explicitly reported.

## 15. Known limitations

* A full run needs ~1,100 requests (1,000 book detail pages) → 5–8 minutes at
  the polite default rate. Use `--skip-details` for a 10-second smoke test
  (then `category`/`description` are empty).
* Scraping is single-threaded by design (assignment rule: reasonable request
  rates); no checkpoint/resume — a crashed run restarts from page 1.
* Duplicate detection is exact-after-normalisation; fuzzy/near-duplicate
  matching (e.g. Levenshtein) is intentionally out of scope for this
  medium-level build.
* The sites are demo sandboxes; data has no real-world meaning (the sites say
  so themselves).
* No database integration — output is CSV + JSON as required.

## 16. AI usage summary

AI (Claude, OpenCode agent) was used as allowed by the assignment: designing
the schema and module layout, generating first drafts of scraper/cleaning
code, and reviewing selectors against the live HTML. All AI output was
reviewed and tested — notably a BeautifulSoup `tag.get("classes")` bug was
caught and fixed (`class` is the correct attribute), and one test expectation
was corrected after checking the real `page-2.html` markup. Full details,
prompts and verification steps are in [`AI_USAGE.md`](AI_USAGE.md).
