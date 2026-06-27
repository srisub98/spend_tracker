# Finance Tracker — Project Brief

A local-only personal finance tracker. Upload CSV bank/credit/brokerage statements, auto-categorize transactions, track net worth over time, and log bill splits with friends. Exports a summary Excel workbook and a self-contained HTML dashboard (for phone viewing via iCloud).

> **Roadmap:** `docs/PRD.md` (phases 0–6, all done or absorbed as of 2026-06-10) and
> **`docs/PRD-2.md`** (the active plan: true-spend bill settlement, Vanguard statement PDF
> import + investment ledger/cost basis, 30,000-ft allocation + critic, spending insights).
> Read the relevant PRD before starting feature work — schema changes, decisions, and
> acceptance criteria live there. Historical sheet data for validation:
> `data/bootstrap/sheet_raw_pull_2026-06-09.md`.
>
> **Git & data safety (updated 2026-06-25):** this is now a shareable repo
> (`srisub98/spend_tracker`, private). The whole `data/` tree, `.env`, and `*.db` are
> git-ignored — **never commit real financial data.** Synthetic, non-personal sample
> files for the test suites live in `tests/fixtures/`. Before committing, sanity-check
> `git status`/`git ls-files` for anything under `data/` or any secret. **When writing or
> updating docs (PRDs, design notes, examples), always use anonymized/sample financial
> data — never real balances, account numbers, last-4s, or employer names.**

## Design standard (2026-06-10)

The UI follows the **minimalist warm-neutral design system** in `docs/design/DESIGN.md`
(from the author's design handoff; tokens live in `static/css/main.css` `:root`, interactions in
`static/js/main.js`). Core rules when touching any template:
- **Accent is near-black (`--ink`)** — buttons, active nav, hero cards, focus rings.
  Green (`--pos`)/red (`--neg`) appear ONLY on numeric figures and trend chips, never on chrome.
- Reuse the existing class vocabulary: `.stat-card` (+`.is-hero`), `.trend`, `.spark`,
  `.card`, `.table-wrap`, `.data-table`, `.pivot-table`, `.badge-*`, `.list-row`, `.reveal`.
- Animations (count-ups via `data-count`, sparklines via `data-values`, scroll reveals)
  are gated behind `html.js` + `prefers-reduced-motion` — pages must render fully without JS.
- Charts go through `FT.theme()` / `FT.colors()` (tonal scale, ink tooltips), Chart.js is
  vendored at `static/js/chart.umd.min.js` and loaded once in `base.html`.

## Running the app

```bash
make install    # one-time: creates .venv, installs requirements
make run        # starts Flask — open http://localhost:5001
```

`make help` lists all targets (bootstrap, bootstrap-reset, db-shell, reset-db, clean).
See README.md for the human-facing quickstart.

Notes for this machine: use `python3`/`make` (no `python` alias), and the app runs on
**port 5001** (`PORT` in `.env`) because macOS AirPlay Receiver squats on 5000 answering 403s.
Historical data was bootstrapped from `data/bootstrap/expenses.xlsx` via
`scripts/bootstrap_from_sheet.py` (re-runnable with `--reset`); sheet aggregates are
authoritative for months before `LIVE_START_MONTH=2026-05`.

## Testing & CI

```bash
.venv/bin/pip install -r requirements-dev.txt   # pytest
.venv/bin/python -m pytest                       # Python unit + integration tests
npm install && npx playwright install chromium   # one-time, for e2e
PYTHON=.venv/bin/python npx playwright test       # browser e2e (boots its own server)
```

- **pytest** (`tests/python/`) covers the CSV parser, rules ordering, the provider
  storage helper, the holdings parser, and a full upload→confirm→dedup flow via the
  Flask test client. `conftest.py` binds each test to a fresh temp DB and blanks
  `ANTHROPIC_API_KEY`, so the suite is hermetic (the categorizer never calls the network).
- **Playwright** (`tests/e2e/`) drives the real app; `playwright.config.ts`'s `webServer`
  recreates a throwaway DB (`data/e2e_test.db`) seeded by `scripts/seed_test_db.py` with
  demo accounts, so e2e never touches real data. Locally pass `PYTHON=.venv/bin/python`.
- **Mock data** lives in `tests/fixtures/` (one CSV per parser path + a Schwab holdings
  export) — synthetic and safe to commit. See its README for what each file exercises.
- **Demo dataset** (`scripts/seed_test_db.py seed_demo_data()`, run via `--demo`) layers a
  richer synthetic dataset — sheet history, live transactions, net-worth snapshots +
  holdings, and bill splits — on top of the demo accounts so the dashboard, net-worth,
  splits, and Excel/HTML exporters render real content. It's kept out of `seed_accounts()`
  so the hermetic suite stays green; report tests opt in via the `demo_app`/`demo_client`
  pytest fixtures, and the Playwright webServer seeds it automatically. Covered by
  `tests/python/test_exports.py` and `tests/e2e/reports.spec.ts`.
- **CI** (`.github/workflows/ci.yml`) runs pytest and Playwright on push/PR.
- **Uploads are partitioned by provider** via `services/storage.py` (`upload_path()`):
  transaction CSVs land in `data/uploads/<provider-slug>/` (slug from the account's
  institution), holdings/statements in `data/uploads/{holdings,statements}/`.

## Environment setup

Copy `.env.example` to `.env` and fill in:
```
ANTHROPIC_API_KEY=your_key_here
OUTPUT_FOLDER=data/exports
DB_PATH=data/finance.db
LIVE_START_MONTH=2026-06   # cutover: dashboard months before this come from sheet bootstrap
PORT=5001                  # optional; default 5000
```

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask |
| Database | SQLite (single file, `data/finance.db`) |
| Data processing | pandas |
| Excel export | openpyxl |
| AI categorization | Claude API (`claude-sonnet-4-6`) via `anthropic` SDK |
| Charts (browser) | Chart.js via CDN |
| Charts (static HTML) | Chart.js embedded inline |

No ORM. Plain parameterized SQL with `sqlite3.Row`.

---

## File Structure

```
finance-tracker/
├── app.py                        # Entry point — registers blueprints, inits DB, runs Flask
├── config.py                     # Loads .env: DB_PATH, OUTPUT_FOLDER, LIVE_START_MONTH, PORT, etc.
├── requirements.txt
├── requirements-dev.txt          # pytest, for tests/python/
├── .env.example
├── CLAUDE.md                     # This file
│
├── Makefile                      # install / run / bootstrap / db-shell / reset-db
├── README.md                     # Human-facing quickstart
│
├── docs/
│   ├── PRD.md                    # Phases 0–6 roadmap (done/absorbed)
│   ├── PRD-2.md                  # Active roadmap: true-spend splits, Vanguard PDF import, 30k-ft allocation, insights
│   └── design/                   # DESIGN.md — the warm-neutral design system spec
│
├── scripts/
│   ├── bootstrap_from_sheet.py   # One-time import of the old Google Sheet (xlsx)
│   └── seed_test_db.py           # Seeds demo accounts + synthetic demo dataset (--demo); used by e2e and dev
│
├── data/                         # real financial data — repo never goes to git
│   ├── uploads/                  # Raw uploaded files, partitioned by provider (services/storage.py)
│   ├── exports/                  # Generated Excel and HTML files
│   ├── bootstrap/                # expenses.xlsx + raw sheet pull (bootstrap inputs)
│   └── finance.db                # SQLite database (auto-created on first run)
│
├── database/
│   ├── db.py                     # get_db()/init_db(), additive column migrations, category+rule seeding
│   ├── schema.sql                # All CREATE TABLE statements
│   └── seed_data.py              # CATEGORY_SEED — canonical category list
│
├── models/
│   ├── transaction.py            # CRUD + bulk insert + Plaid insert/dedup + query helpers
│   ├── account.py                # CRUD + csv_mapping persistence + Plaid linkage
│   ├── category.py               # Reads the categories registry
│   ├── rule.py                   # Reads/writes the rules registry
│   ├── aggregates.py             # Unified cashflow reads (sheet history + live txs, true-spend aware) — dashboards read ONLY through here
│   ├── net_worth.py              # Snapshot CRUD + year grid + asset-class series + holdings
│   ├── bill_split.py             # Outing/participant/line-item CRUD + people registry + per-person ledger/settlement
│   ├── investment.py             # Investment ledger CRUD (trades/dividends/transfers) + YTD income/deposit rollups
│   ├── budget.py                 # Per-category monthly budget targets, seedable from prior-year history
│   ├── life.py                   # "Life tab" fixed/needed monthly costs + payment logging + coverage gaps
│   └── plaid_item.py             # Plaid Item storage (access_token + sync cursor per linked institution)
│
├── services/
│   ├── csv_parser.py             # CSV ingestion: normalize columns, apply rules, dedup insert
│   ├── rules.py                  # SEED_RULES + DB rule loading/matching (run BEFORE Claude)
│   ├── categorizer.py            # Claude API batching — only called for unmatched transactions
│   ├── recurring.py              # Recurring-charge/subscription detection (cadence + amount stability)
│   ├── critic.py                 # Rule-based investment checks (e.g. employer-stock concentration look-through)
│   ├── holdings_parser.py        # Schwab/Vanguard holdings CSV parsers
│   ├── vanguard_pdf.py           # Vanguard monthly statement PDF parser (cost basis, trades, deposits)
│   ├── schwab_api.py             # Schwab Trader API OAuth client (balances + positions sync)
│   ├── plaid_api.py              # Plaid client — link/sync/map, all gated behind configured()
│   ├── storage.py                # upload_path() — partitions uploads by provider/bucket under data/uploads/
│   ├── excel_exporter.py         # openpyxl workbook builder (multi-sheet)
│   └── html_exporter.py          # Self-contained HTML dashboard (Chart.js inlined)
│
├── routes/
│   ├── dashboard.py              # /dashboard/*
│   ├── transactions.py           # /transactions/*
│   ├── rules.py                  # /rules/*
│   ├── accounts.py               # /accounts/*
│   ├── plaid.py                  # /plaid/* (404s unless services/plaid_api.configured())
│   ├── net_worth.py              # /net-worth/*
│   ├── investments.py            # /investments/*
│   ├── insights.py               # /insights/*
│   ├── life.py                   # /life/*
│   ├── bill_splits.py            # /splits/*
│   └── exports.py                # /export/*
│
├── templates/
│   ├── base.html                  # Shared layout + nav
│   ├── dashboard/
│   │   └── index.html             # Sheet-parity cashflow, quarters, recurring, budget strip
│   ├── transactions/
│   │   ├── index.html             # Filterable transaction list
│   │   ├── upload.html            # Upload form
│   │   ├── preview.html           # Column-mapping/sign-flip preview before insert
│   │   └── review.html            # Review/correct Claude-assigned categories
│   ├── rules/
│   │   └── index.html             # Registry: list, add/edit form, dry-run test
│   ├── accounts/
│   │   └── index.html
│   ├── net_worth/
│   │   ├── index.html             # Net worth chart + snapshot entry form + holdings table
│   │   ├── equities.html          # 30,000-ft allocation, positions/gains, critic checks — rendered by routes/investments.py
│   │   ├── holdings_preview.html  # Schwab/Vanguard holdings CSV preview
│   │   └── statement_preview.html # Vanguard statement PDF preview
│   ├── investments/
│   │   └── activity.html          # Investment ledger + ledger-vs-cashflow reconciliation
│   ├── insights/
│   │   └── index.html             # Top merchants, category trends, subscriptions, budgets, cut candidates
│   ├── life/
│   │   └── index.html             # Fixed/needed monthly costs + coverage gaps
│   ├── splits/
│   │   ├── index.html             # List of outings + who owes you total
│   │   ├── detail.html            # Single outing: line items, per-person totals, mark paid
│   │   └── people.html            # Per-person ledger across outings + settle/Venmo handle
│   └── export/
│       └── index.html             # Export buttons + last-exported timestamps
│
└── static/
    ├── css/main.css
    └── js/
        ├── main.js
        └── chart.umd.min.js        # Vendored Chart.js, loaded once in base.html
```

---

## Database Schema

### `accounts`
Tracks each financial account (checking, savings, credit card, brokerage, loan).

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | e.g. "Chase Checking" |
| type | TEXT | checking / savings / credit / brokerage / loan / other |
| institution | TEXT | e.g. "Chase" |
| currency | TEXT | default USD |
| is_liability | INTEGER | 1 = subtract from net worth |
| asset_class | TEXT | stocks / cash / retirement / other / NULL — net-worth rollup |
| external_ref | TEXT | institution account # (last 4) — routes holdings CSVs |
| flip_amount_signs | INTEGER | 1 = negate amounts on CSV import (issuer sign conventions) |
| csv_mapping | TEXT | JSON column mapping saved from import preview (per-bank CSV formats) |
| plaid_account_id | TEXT | Plaid account this row syncs from (NULL = CSV-only) |
| plaid_item_id | TEXT | owning `plaid_items.item_id` |
| created_at | TEXT | ISO8601 |

> **Plaid sync (optional).** With `PLAID_*` set in `.env`, the Accounts page can link a
> bank (`plaid_items` table holds the access_token + `/transactions/sync` cursor) and
> auto-pull transactions through the same rules → Claude → review pipeline as CSVs.
> `transactions.plaid_transaction_id` makes re-syncs idempotent, and
> `models.transaction.insert_plaid_rows()` skips any Plaid txn already imported from a
> CSV (matched on amount + date ±3d, since Plaid's clean merchant name won't byte-match a
> raw memo). Everything is gated behind `services/plaid_api.configured()` — unset = no
> Plaid surface, app is CSV-only. See `services/plaid_api.py`, `routes/plaid.py`.

### `categories`
Canonical category registry (replaces the old `config.CATEGORIES` constant). Seeded from
`database/seed_data.py` on first init; names match the author's Google Sheet. `kind` is one of
`expense` / `income` / `transfer` (neutral, excluded from spend+income) / `investment`
(money into brokerage; net income − investments = FCF).

### `rules`
Editable categorization rules: `pattern`, `match_type` (substring/regex), `category`,
`priority` (lower = checked first), `active`. Seeded from `services/rules.py SEED_RULES`
on first init. First match wins, ordered by (priority, id).

### `monthly_summaries`
Historical monthly aggregates bootstrapped from the Google Sheet (`month`, `category`,
`kind`, `amount`, `source='sheet'`). Dashboards read these for months before
`LIVE_START_MONTH` and live transactions after (see docs/PRD.md §5).

### `holdings`
Brokerage positions attached to a net-worth snapshot (filled by holdings CSV import,
PRD Phase 4): `snapshot_id`, `account_id`, `symbol`, `quantity`, `price`, `market_value`,
`asset_type`, `cost_basis` (NULL when the source file doesn't provide it, e.g. Vanguard's CSV).

### `holding_overrides`
Per-symbol asset-type override — the "rule engine for holdings": set from the Investments
page, applied at read time over every snapshot's holdings (e.g. force a bond ETF to count
as `other`, or a fund to count as `cash`). Columns: `symbol` (PK), `asset_type` (equity /
etf / mutual_fund / cash / other), `created_at`.

### `investment_transactions`
Investment ledger (PRD-2 Phase 8): every trade/dividend/transfer at any brokerage —
parsed from a Vanguard statement PDF, pulled from the Schwab API, or entered manually.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK | → accounts |
| date | TEXT | trade date, YYYY-MM-DD |
| settle_date | TEXT | |
| symbol | TEXT | NULL for cash movements |
| type | TEXT | buy / sell / dividend / capgain_st / capgain_lt / interest / deposit / withdrawal / fee / other |
| quantity | REAL | |
| price | REAL | |
| fees | REAL | |
| amount | REAL | signed: buys negative, deposits positive |
| source | TEXT | 'vanguard_pdf' / 'schwab_api' / 'manual' |
| raw | TEXT | original parsed line (audit trail) |
| created_at | TEXT | ISO8601 |

**UNIQUE constraint:** `(account_id, date, symbol, type, amount)` — re-importing the same statement is safe.

### `transactions`
One row per transaction, imported from CSV or synced via Plaid.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER FK | → accounts |
| date | TEXT | YYYY-MM-DD |
| description | TEXT | raw payee/memo from CSV, or Plaid's merchant name |
| amount | REAL | positive = money in, negative = money out |
| currency | TEXT | default USD |
| category | TEXT | assigned by rules, Claude, or user |
| category_source | TEXT | 'rule' / 'claude' / 'user' / NULL |
| notes | TEXT | user-added notes |
| raw_csv_row | TEXT | JSON of original CSV row (audit trail) — NULL for pure-Plaid rows |
| import_batch_id | TEXT | UUID per upload session |
| plaid_transaction_id | TEXT | Plaid's stable id — set on Plaid-origin rows, or adopted onto a matching CSV row by `insert_plaid_rows()` (see `accounts` note above) |
| my_share | REAL | True spend (PRD-2 Phase 7): this transaction's actual cost after splitting with friends via `/transactions/<id>/split`. NULL = unsplit, full `amount` is yours. `models/aggregates.py` reads `COALESCE(my_share, amount)` everywhere |
| created_at | TEXT | ISO8601 |

**UNIQUE constraint:** `(account_id, date, description, amount)` — re-uploading the same CSV is safe.

### `net_worth_snapshots`
Point-in-time net worth records. Snapshot-based (not computed from transactions) because brokerage values change with market movements, not just transactions.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| snapshot_date | TEXT | YYYY-MM-DD |
| total_assets | REAL | |
| total_liabilities | REAL | |
| net_worth | REAL | assets - liabilities |
| notes | TEXT | |
| source | TEXT | 'manual' / 'sheet' (bootstrap) / 'holdings_csv' |

### `snapshot_account_balances`
Per-account balance tied to a snapshot.

| Column | Type | Notes |
|---|---|---|
| snapshot_id | INTEGER FK | → net_worth_snapshots |
| account_id | INTEGER FK | → accounts |
| balance | REAL | |

### `schwab_tokens`
Schwab Trader API OAuth tokens (PRD Phase 4b) — single row, local DB only (gitignored).

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | CHECK(id = 1) — enforces a single row |
| access_token | TEXT | |
| refresh_token | TEXT | |
| access_expires_at | TEXT | ISO8601; access tokens live ~30 min |
| refresh_expires_at | TEXT | ISO8601; refresh tokens live 7 days → weekly re-login |
| updated_at | TEXT | |

### `plaid_items`
One row per linked institution login (a Plaid "Item"). Local DB only (gitignored) —
`access_token` is a long-lived bearer secret. `cursor` drives incremental `/transactions/sync` calls.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| item_id | TEXT UNIQUE | Plaid's Item id |
| access_token | TEXT | |
| institution | TEXT | |
| cursor | TEXT | `/transactions/sync` cursor; NULL = full sync |
| status | TEXT | default 'active' |
| created_at | TEXT | ISO8601 |
| updated_at | TEXT | |

### `budgets`
Per-category monthly budget targets (PRD-2 Phase 10), shown against actual spend on the
Insights and Dashboard pages. Columns: `category` (PK), `monthly_amount`, `active`.

### `life_items`
The "Life tab": declared fixed/needed monthly spend (rent, insurance, internet, ...) —
these often never appear in a CSV (e.g. rent paid by check/Zelle), so `/life/<id>/log` can
post one as a transaction for a given month. Columns: `name`, `monthly_amount`, `category`
(optional canonical category), `notes`, `active`.

### `people`
Friends registry (PRD-2 Phase 7) — settlement is tracked per-person across every outing,
not just within one. Legacy name-only `outing_participants` rows get linked here by
`backfill_people()`.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE | |
| venmo_handle | TEXT | |
| notes | TEXT | |
| created_at | TEXT | ISO8601 |

### `outings`
A shared expense event (dinner, trip, etc.).

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| title | TEXT | e.g. "Dinner at Nobu" |
| outing_date | TEXT | YYYY-MM-DD |
| notes | TEXT | |

### `outing_participants`
People at an outing. You are always the one owed money.

| Column | Type | Notes |
|---|---|---|
| outing_id | INTEGER FK | → outings |
| name | TEXT | friend's name |
| person_id | INTEGER FK | → people, nullable — legacy rows are name-only until `backfill_people()` links them |
| is_paid | INTEGER | 0 = owes you, 1 = settled |
| paid_at | TEXT | ISO8601 when marked paid |

### `outing_line_items`
Individual expenses within an outing.

| Column | Type | Notes |
|---|---|---|
| outing_id | INTEGER FK | → outings |
| description | TEXT | e.g. "Dinner bill" |
| total_amount | REAL | |
| paid_by_me | INTEGER | 1 = you fronted this cost |
| split_count | INTEGER | how many ways to split |
| per_person_amount | REAL | computed or manually overridden |
| transaction_id | INTEGER FK | → transactions, nullable — set when this line item was auto-created by `/transactions/<id>/split` |

---

## Categorization Strategy

### Step 1 — Rules registry (`rules` DB table)
Checked first, no API call. Rules live in the DB (seeded from `services/rules.py
SEED_RULES` on first init; editing UI lands in PRD Phase 3). Each rule: pattern,
match_type (substring = case-insensitive contains, regex), category, priority. Checked
in (priority, id) order, first match wins — so e.g. "uber eats" → Food is seeded before
"uber" → Car. `services/rules.py load_rules()` compiles active rules once per import.

### Step 2 — Claude API (`services/categorizer.py`)
Only transactions with no rule match go to Claude. Batched in groups of 50; valid
category names come from the `categories` table, and responses outside that list are
dropped. Failures (bad key, parse errors) surface as flash messages — never silently.
Category source is set to `'claude'`.

### Step 3 — User review
`/transactions/review` shows all `claude`-categorized transactions for confirmation. User can correct and save (sets source to `'user'`).

---

## Flask Routes

### Dashboard
| Method | Path | Purpose |
|---|---|---|
| GET | /dashboard?year=YYYY | Home (`/` redirects here). Sheet-parity cashflow: income/expense pivots, % of income, FCF, cumulative, quarter-over-quarter + YoY, recurring-charge detection, budget strip. Reads via `models/aggregates.py` (sheet history < LIVE_START_MONTH, transactions after) |

### Transactions
| Method | Path | Purpose |
|---|---|---|
| GET | /transactions | Paginated list with filters (account, category, date range, review status) |
| GET, POST | /transactions/upload | GET: upload form. POST: parse CSV → **preview** (no insert): sample rows, column-mapping dropdowns, sign-flip. Re-posts to itself to re-preview |
| POST | /transactions/upload/confirm | Insert previewed file; optionally persist mapping+flip to the account; hands unmatched rows to Claude |
| GET | /transactions/review | Review Claude-categorized transactions |
| POST | /transactions/bulk-category | Mass-categorize selected transactions (e.g. from Needs Review) and suggest a shared rule pattern for future imports |
| POST | /transactions/\<id\>/category | AJAX: update category, set source='user' |
| POST | /transactions/\<id\>/delete | Delete a transaction |
| POST | /transactions/\<id\>/split | True spend (PRD-2 Phase 7): split a card charge with friends — creates/links an outing, sets `my_share` |
| POST | /transactions/\<id\>/unsplit | Remove a split — the full charge counts as your expense again |

### Rules
| Method | Path | Purpose |
|---|---|---|
| GET | /rules | Registry UI: list, add/edit form (supports ?pattern=&category= prefill from review, ?edit=id) |
| POST | /rules, /rules/\<id\>/edit, /rules/\<id\>/delete, /rules/\<id\>/toggle | CRUD |
| GET | /rules/test?pattern=&match_type= | Dry-run a pattern against all transactions (JSON: count + samples) |
| POST | /rules/reapply | Re-categorize rule/claude/NULL-sourced transactions; never touches user-sourced |

### Accounts
| Method | Path | Purpose |
|---|---|---|
| GET | /accounts | List accounts |
| POST | /accounts | Create account |
| POST | /accounts/\<id\>/edit | Update account |
| POST | /accounts/\<id\>/delete | Delete (only if no transactions) |

### Plaid (optional — all routes 404 unless `services/plaid_api.configured()`)
| Method | Path | Purpose |
|---|---|---|
| POST | /plaid/link-token | JSON link_token for the browser Plaid Link flow |
| POST | /plaid/exchange | Exchange public_token → store Item + auto-create/link accounts |
| POST | /plaid/sandbox-link | Sandbox-only: link a fake bank with no Link UI (testing) |
| POST | /plaid/sync | Cursor sync all Items → dedup-aware insert → Claude → flash summary |
| POST | /plaid/\<item_id\>/unlink | Soft-unlink an Item (keeps synced transactions) |

### Net Worth
| Method | Path | Purpose |
|---|---|---|
| GET | /net-worth?year=YYYY | Stat cards, stacked class chart, account × month grid, holdings table, prefilled snapshot form |
| POST | /net-worth/snapshot | Record balances — MERGES into existing snapshot of same date (upsert) |
| GET | /net-worth/equities | Legacy URL, kept working — redirects to `/investments` |
| POST | /net-worth/equities/vest | Log an RSU vest as an income transaction (category "RSU Vest"); vests never appear in checking/card CSVs |
| POST | /net-worth/equities/classify | AJAX: set a per-symbol `holding_overrides` asset-type override |
| POST | /net-worth/schwab/exchange | Finish the Schwab OAuth flow (user pastes the redirect URL) |
| POST | /net-worth/schwab/sync | Pull balances + positions for all Schwab accounts into today's snapshot |
| POST | /net-worth/statement/preview | Vanguard statement PDF → preview holdings w/ cost basis + parsed trades/deposits |
| POST | /net-worth/statement/confirm | Write statement holdings into the dated snapshot + new rows into the investment ledger |
| POST | /net-worth/holdings/preview | Upload Schwab/Vanguard holdings CSV → preview (account matching via external_ref) |
| POST | /net-worth/holdings/confirm | Write balances + holdings rows into the dated snapshot |
| GET | /net-worth/data | JSON time-series for Chart.js |

### Investments
| Method | Path | Purpose |
|---|---|---|
| GET | /investments | The 30,000-ft view (PRD-2 Phase 9): allocation by class/account, positions with gains, YTD vests/income, the rule-based critic |
| GET | /investments/activity | Investment ledger, filterable by year/account/type, with a ledger-vs-cashflow reconciliation |

### Insights
| Method | Path | Purpose |
|---|---|---|
| GET | /insights | Top merchants, category trends vs your 3/12-mo average + YoY, budgets vs actual, subscription audit, ranked cut candidates (PRD-2 Phase 10) |
| POST | /insights/budgets | Save per-category monthly budget targets |

### Life
| Method | Path | Purpose |
|---|---|---|
| GET | /life | Fixed/needed monthly cost items + coverage gaps vs income/spend |
| POST | /life | Add a fixed-cost item |
| POST | /life/\<id\>/edit | Update an item |
| POST | /life/\<id\>/delete | Delete an item |
| POST | /life/\<id\>/log | Log a payment (e.g. rent via check/Zelle) as a transaction for a given month — these never appear in CSVs |

### Bill Splits
| Method | Path | Purpose |
|---|---|---|
| GET | /splits | All outings + total owed to you |
| GET | /splits/people | Per-person ledger across every outing, with settle/Venmo handle |
| POST | /splits/people/\<id\>/settle | Mark all of that person's outstanding items paid |
| POST | /splits/people/\<id\>/venmo | Save a person's Venmo handle |
| POST | /splits/new | Create outing |
| GET | /splits/\<id\> | Outing detail: items, per-person totals |
| POST | /splits/\<id\>/item | Add line item |
| POST | /splits/\<id\>/item/\<item_id\>/delete | Delete a line item |
| POST | /splits/\<id\>/participant | Add participant |
| POST | /splits/\<id\>/participant/\<pid\>/paid | Mark participant as paid |
| POST | /splits/\<id\>/participant/\<pid\>/unpaid | Undo — mark participant unpaid |
| POST | /splits/\<id\>/delete | Delete outing |

### Exports
| Method | Path | Purpose |
|---|---|---|
| GET | /export | Export UI |
| POST | /export/excel | Generate Excel → save to data/exports/ |
| POST | /export/html | Generate self-contained HTML → save to data/exports/ |

---

## Excel Export Sheets

1. **All Transactions** — full table with filters enabled
2. **Spending by Category** — monthly pivot (category × month, totals)
3. **Net Worth History** — snapshot table + chart
4. **Outstanding Splits** — who owes you, how much, from which outing

---

## Static HTML Export

- Single `.html` file, no server needed
- All data embedded as inline JSON in `<script>` tags
- Chart.js minified source embedded inline (no CDN needed offline)
- Key stats: current net worth, monthly spend, top categories, who owes you
- Saved to `data/exports/finance_dashboard_YYYYMMDD.html`
- Future: configure `OUTPUT_FOLDER` to iCloud Drive path for phone access

---

## Key Architectural Decisions

- **No ORM** — raw parameterized SQL keeps things auditable and dependency-light
- **Snapshot-based net worth** — handles brokerage accounts where value changes without transactions
- **Dedup via UNIQUE constraint** — re-uploading a CSV never creates duplicates
- **Rules before Claude** — static rules handle 70-80% of transactions with zero token cost
- **pandas only in services** — not imported in models or routes; keeps mental model clean
- **Single `python3 app.py` command** — no migration step; categories/rules seed automatically on first init
- **No auth** — local only, localhost, single user
- **Plaid sync mirrors the Schwab integration pattern** — a single `configured()` predicate
  gates both the routes (404 if unset) and the template UI, so an external API integration
  is always strictly additive: unset env vars reproduce yesterday's app exactly
- **Person-specific behavior is config-gated, never hardcoded** — e.g. `EMPLOYER_STOCK_SYMBOL`
  (investments-page concentration check in `services/critic.py`) is blank by default and the
  check no-ops entirely until set, so the app has no baked-in assumptions about who's running it
