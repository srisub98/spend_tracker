# Mock fixtures

Synthetic, **non-personal** sample files used by the test suites. Safe to commit —
no real account numbers, balances, or transactions. Real statements live in
`data/` (git-ignored) and never belong here.

Each transaction CSV exercises a different code path in
[`services/csv_parser.py`](../../services/csv_parser.py):

| File | Format it exercises |
|---|---|
| `citi-checking.csv` | separate Debit/Credit columns, `MM-DD-YYYY` dates, trailing comma |
| `citi-doublecash.csv` | single signed `Amount` column (purchases negative) |
| `amex.csv` | single `Amount` with charges **positive** → needs `flip_amount_signs` |
| `capitalone.csv` | unsigned `Transaction Amount` + `Transaction Type` (Credit/Debit) |
| `unmatched.csv` | descriptions no seed rule matches → land in `/transactions/review` |
| `schwab-positions.csv` | Schwab "Positions" holdings export ([`holdings_parser.py`](../../services/holdings_parser.py)) |

The accounts these map to (by `institution`) are created by
[`scripts/seed_test_db.py`](../../scripts/seed_test_db.py).

## Demo dataset (richer, report-driving)

The per-parser CSVs above are tiny on purpose. For tests that need *populated*
pages — the dashboard, net-worth grid, splits, and the Excel/HTML exporters —
`scripts/seed_test_db.py` also ships `seed_demo_data()`, a fully synthetic,
non-personal dataset layered on top of the demo accounts:

- **Sheet history** — `monthly_summaries` for all of 2025 + Jan–May 2026
  (everything before `LIVE_START_MONTH`), with income/expense/investment +
  quarterly RSU vests.
- **Live transactions** — ~23 June-2026 rows across every category, categorized
  through the real rule engine; two unmatched rows simulate Claude output so they
  surface in `/transactions/review`. Kept small so they never push the upload
  fixtures off page 1 of `/transactions`.
- **Net-worth snapshots** — Jan–Jun 2026, per-account balances (cash / stocks /
  retirement / liabilities) plus Schwab holdings (VTI/AAPL/cash) on the latest one.
- **Bill splits** — three outings with a mix of paid/unpaid participants
  (an $850 outstanding receivable).

It is **kept out of `seed_accounts()`** so the hermetic pytest suite (which
assumes empty tables) stays green. Consume it via:

- **pytest** — the `demo_app` / `demo_client` fixtures (`tests/python/conftest.py`).
- **Playwright** — the webServer runs `seed_test_db.py --demo` (`playwright.config.ts`).
- **manually** — `DB_PATH=data/scratch.db python scripts/seed_test_db.py --demo`
  (never point it at a real DB).

All figures are made-up round numbers — safe to commit.
