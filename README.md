# Spend Tracker

[![CI](https://github.com/srisub98/spend_tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/srisub98/spend_tracker/actions/workflows/ci.yml)

A **local-only** personal finance tracker. Upload your bank / credit-card / brokerage
CSV statements, auto-categorize transactions with an editable rules registry (with the
Claude API as an optional fallback), track net worth across accounts, split bills with
friends, and export an Excel workbook or a self-contained HTML dashboard.

Everything runs on your machine — **Flask + SQLite, no cloud, no accounts, no auth.**
Your financial data never leaves your computer.

> ⚠️ **Your data stays local.** The entire `data/` directory (uploads, the SQLite DB,
> exports) and your `.env` are git-ignored. Nothing personal is committed. The only
> sample data in this repo is synthetic and lives in [`tests/fixtures/`](tests/fixtures/).

## Features

- **CSV import with preview** — see exactly how a statement parses *before* anything is
  saved; map columns for new banks and remember the mapping per account. Re-uploading
  overlapping statements is safe (duplicates are skipped via a DB uniqueness constraint).
- **Plaid bank sync (optional)** — connect a bank from the Accounts page to auto-pull
  transactions instead of uploading CSVs; both work side by side. Synced rows run through
  the same rules → Claude → review pipeline, and a sync never re-imports a transaction a
  CSV already brought in (matched on amount + date). Off unless `PLAID_*` is set in `.env`.
- **Rules-first categorization** — a fast, editable substring/regex rules registry handles
  most transactions with zero API cost; anything left over can optionally go to the Claude
  API, then to a review queue you confirm.
- **Net worth** — point-in-time snapshots across accounts, a stacked asset-class chart, and
  a per-account month grid. Import brokerage **holdings CSVs** or a **Vanguard statement
  PDF** (with cost basis), or sync Schwab directly via their free official API.
- **Bill splits** — front a group bill, split any charge, and track who owes you on a
  per-person "Settle Up" page.
- **Insights & exports** — spending trends, top merchants, a subscription audit, plus an
  Excel workbook and an offline HTML dashboard you can open on your phone.

## Quickstart

Requires Python 3.11+.

```bash
git clone https://github.com/srisub98/spend_tracker.git
cd spend_tracker
make install          # creates .venv and installs dependencies
cp .env.example .env  # then edit (see notes below)
make run              # open the printed URL (default http://localhost:5001)
```

The SQLite database, categories, and rules are created automatically on first run.
Create your accounts, then upload statements at **Transactions → Upload**.

### `.env` notes

- `ANTHROPIC_API_KEY` — **optional**. Without it, transactions no rule matched are simply
  left for manual review (no errors). Get one at [console.anthropic.com](https://console.anthropic.com).
- `PORT` — defaults to 5000; the example uses **5001** because macOS AirPlay Receiver
  occupies 5000.
- `LIVE_START_MONTH`, `SCHWAB_*`, `PLAID_*` — see comments in `.env.example` (only needed
  for the optional history-bootstrap, Schwab-sync, and Plaid bank-sync features). Plaid
  Sandbox is free with fake data, and real banks are free too under Plaid's no-cost
  Trial plan (up to 10 linked banks); leave `PLAID_*` blank to stay CSV-only.

## Bring your own statements

Uploaded files are stored locally, **partitioned by provider**:

```
data/uploads/<provider>/     transaction CSVs (provider = the account's institution)
data/uploads/holdings/       brokerage holdings CSVs
data/uploads/statements/     statement PDFs
```

Adding a new bank? Create the account, upload an example CSV, and if the columns aren't
auto-detected, map Date / Description / Amount (or Debit / Credit) on the preview screen
and tick **"remember these settings"** — future uploads for that account parse
automatically. The parser already handles common Citi, Amex, Capital One, and Schwab
formats (see [`tests/fixtures/`](tests/fixtures/) for examples of each shape).

## Testing

Two suites, both run in CI on every push/PR:

```bash
# Python — parser, rules, storage, holdings, and an upload→confirm→dedup flow
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest

# End-to-end — Playwright drives the real app against a throwaway, seeded DB
npm install
npx playwright install chromium
PYTHON=.venv/bin/python npx playwright test
```

The e2e harness boots its own Flask server on a disposable database seeded by
`scripts/seed_test_db.py`, so tests never touch your real data. Pass
`PYTHON=.venv/bin/python` locally so the test server uses your virtualenv.

## Project layout

```
app.py            Flask entry point
config.py         .env loading
database/         schema.sql, connection lifecycle, seed data
models/           one module per table — plain parameterized SQL, no ORM
services/         CSV parsing, rules engine, Claude categorizer, storage, exporters
routes/           Flask blueprints
templates/        Jinja templates
static/           CSS + vendored Chart.js + a little JS
scripts/          bootstrap + test-seed scripts
tests/            pytest (tests/python), Playwright (tests/e2e), fixtures (tests/fixtures)
.github/          CI workflow
data/             SQLite DB, uploads, exports — local only, git-ignored
```

See [CLAUDE.md](CLAUDE.md) for the full schema and conventions, and
[docs/PRD.md](docs/PRD.md) / [docs/PRD-2.md](docs/PRD-2.md) for the roadmap and design
decisions.

## Optional: import existing history

`scripts/bootstrap_from_sheet.py` can import years of prior history from a spreadsheet
(`data/bootstrap/expenses.xlsx`) into monthly aggregates and net-worth snapshots — it was
built for the original author's Google Sheet export, so the column mapping is specific to
that layout. Most users can skip it and just start uploading statements.

## Contributing

This is a personal project shared for others to use and adapt. If you add or edit
documentation (the PRDs, design notes, examples), **use anonymized / sample financial
data only** — never real balances, account numbers, last-4s, or employer names. The
committed docs use illustrative sample figures for exactly this reason.

## License

[MIT](LICENSE) — provided as-is for personal use. No warranty; you are responsible for the
security of your own financial data and any API keys you configure.
