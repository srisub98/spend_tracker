# PRD — Personal Finance Dashboard (Google Sheet replacement)

> **2026-06-10:** Phases 0–5 are done (4b built, awaiting Schwab approval). The next era —
> true-spend bill settlement, Vanguard statement PDF import, investment ledger/cost basis,
> 30,000-ft allocation + critic, spending insights — lives in **`docs/PRD-2.md`**. Phase 6
> below is absorbed into PRD-2 Phase 9.

**Status:** Approved plan, not yet implemented. Written 2026-06-09.
**Audience:** Any future Claude session (any model) or human picking this up cold. Everything needed to execute is in this document plus the codebase. Read `CLAUDE.md` first for the existing architecture.

---

## 1. Goal

Replace Sri's Google Sheets finance tracker ("2022–2026 yearly tabs" workbook) with this local Flask app. Two go-forward workflows, one one-time bootstrap:

1. **Go-forward spending:** upload net-new credit card / bank CSVs monthly → an editable *rules registry* categorizes them (Claude API as fallback) → cashflow dashboard.
2. **Go-forward net worth:** upload Vanguard + Schwab holdings CSVs monthly, type in the handful of accounts that have no CSV → net worth dashboard.
3. **One-time bootstrap:** import the historical monthly aggregates from the Google Sheet (income, expenses by category, per-account balances — all by month) so the dashboard has years of history from day one.

**Critical constraint:** Sri will NOT backfill historical transaction CSVs. History exists only as monthly aggregates from the sheet. The dashboard must seamlessly merge sheet-sourced aggregates (pre-cutover) with transaction-derived aggregates (post-cutover).

---

## 2. The target: what the Google Sheet does

Sheet URL (may require auth; raw pull saved at `data/bootstrap/sheet_raw_pull_2026-06-09.md`):
`https://docs.google.com/spreadsheets/d/1SMGJXxdwLWORwwQHJpS42fTwWZExoutn-jjBYo_HRac`

One tab per year. Each tab contains these blocks (positions vary slightly by year — parse by anchor text, not cell coordinates):

### 2.1 Income block (rows × month columns Jan–Dec)
Rows: `Paycheck 1`, `Paycheck 2`, `Other Income`, `Post Tax RSU Vest` (older tabs also `Interest (CDs/Savings)` / `C1 Interest`), then `Total Income`.

### 2.2 Expenses block (category rows × month columns)
Categories: `Rent + Utilities`, `Home`, `Groceries`, `Food`, `Clothes`, `Entertainment`, `Fitness` (older: "Running /Cycling/Fitness"), `Donations`, `Misc`, `Travel`, `Car`, then `Total Expenses`. Older tabs omit `Home`/`Car` in some years.

### 2.3 Net Income block
`Total Income`, `Total Expenses`, `Expenses as % of Income`, `Total Net Income`, `Investments` (money moved into brokerage that month), `FCF` (= net income − investments), `Cumulative Net Income`.

### 2.4 Year totals + Trends
Per category: total for year, and category as % of yearly income.

### 2.5 Recurring expenses mini-table
Free-form list, e.g. iPhone $50, YT Premium $50 Lemonade $50 Apple $50, Strava $50, PG&E ~$500 ChatGPT $50, car insurance $50 PS Pass $50, Internet $50.

### 2.6 Total Assets grid (account rows × month columns)
Account-level end-of-month balances. Accounts seen across years (names vary, normalize):
`CitiBank` (checking), `CapitalOne Savings`, `CaptialOne Checking` [sic — typo in sheet], `CDs`, `Schwab - personal` (older: "TDAmeritrade / Schwab", "TDAmeritrade"), `Schwab - ExampleCo` (RSU account, appears Nov of prior year), `401K`, `Vanguard`, `Etrade` (closed mid-2024, balance → 0), `Fundrise`, `Venmo/AppleCash`, `Coinbase`.

### 2.7 Net Worth rollup (rows × month columns)
`Net Worth` total plus four asset-class rows: `Stocks`, `Cash`, `Retirement`, `Other`.
Class mapping implied by the sheet's own sums:
- **Stocks** = Schwab personal + Schwab ExampleCo + Vanguard + Etrade + TDAmeritrade
- **Cash** = CitiBank + CapitalOne Savings + CapitalOne Checking + CDs + Venmo/AppleCash
- **Retirement** = 401K
- **Other** = Fundrise + Coinbase

### 2.8 Bill-split mini-tables
Per-person owed amounts. Already covered by the app's existing splits feature — do NOT bootstrap these.

---

## 3. Current codebase state (audited 2026-06-09)

Working skeleton, ~1,400 LOC. DB nearly empty (1 test account, 5 test transactions, 0 snapshots) → **schema changes need no migrations; update `database/schema.sql`, delete `data/finance.db`, re-init.**

What works today:
- CSV transaction upload with column-alias detection (`services/csv_parser.py`), static keyword rules (`services/rules.py`), Claude fallback batching (`services/categorizer.py`), review UI, dedup via `UNIQUE(account_id, date, description, amount)`.
- Manual net-worth snapshots with per-account balances, line chart (`routes/net_worth.py`, `models/net_worth.py`).
- Bill splits, Excel export, self-contained HTML export.

### Known bugs to fix (Phase 0)
1. **`routes/transactions.py:61-68`** — after bulk insert, maps unmatched rows back to DB ids *by description string alone*. Duplicate descriptions (two same-day coffees) collide, and Claude categories can land on wrong rows. Fix: query rows by the `import_batch_id` that was just inserted (already stored per row) and match positionally / by (date, description, amount).
2. **`services/categorizer.py:61`** — `except Exception: return []` swallows everything; a bad API key looks like success. Log the error and surface a flash message ("Claude categorization failed: …"). Also bump `max_tokens` 512 → 1024 (50-item JSON arrays can clip).
3. **Sign conventions** — `services/csv_parser.py` assumes `amount = credit − abs(debit)`. Citi card CSV (`Status, Date, Description, Debit, Credit`): charges in Debit (positive) → comes out negative ✓, but payments appear as Credit `-100` → imports as money *out*, wrong. Amex exports charges as positive in a single Amount column. Add per-account `flip_amount_signs` flag + an import **preview step** (show first ~15 parsed rows with computed signs before committing; user confirms or toggles flip).
4. **`routes/transactions.py:49`** — `file.filename` saved unsanitized; wrap with `werkzeug.utils.secure_filename`. Low risk (local-only) but free to fix.
5. **`templates/net_worth/index.html:60`** — `today` is referenced but never passed by the route; date input renders empty. Pass `today=date.today().isoformat()`.

---

## 4. Data model changes

Add to `database/schema.sql` (wipe + re-init, no migrations):

```sql
-- Canonical categories, replacing the hardcoded config.CATEGORIES list.
-- kind: expense | income | transfer | investment
--   transfer   = neutral, excluded from spend AND income (e.g. CC payment, Venmo)
--   investment = money moved into brokerage; subtracted from net income to get FCF
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    kind       TEXT NOT NULL CHECK(kind IN ('expense','income','transfer','investment')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1
);

-- Editable categorization rules (replaces the static list in services/rules.py,
-- which becomes the seed data).
CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'substring' CHECK(match_type IN ('substring','regex')),
    category   TEXT NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 100,   -- lower = checked first
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Historical monthly aggregates bootstrapped from the Google Sheet.
-- Dashboard reads these for months < LIVE_START_MONTH, transactions after.
CREATE TABLE IF NOT EXISTS monthly_summaries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    month    TEXT NOT NULL,              -- 'YYYY-MM'
    category TEXT NOT NULL,              -- canonical category OR income line name
    kind     TEXT NOT NULL CHECK(kind IN ('expense','income','investment')),
    amount   REAL NOT NULL,              -- always positive
    source   TEXT NOT NULL DEFAULT 'sheet',
    UNIQUE(month, category, source)
);

-- Brokerage positions, attached to a net-worth snapshot.
CREATE TABLE IF NOT EXISTS holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id  INTEGER NOT NULL REFERENCES net_worth_snapshots(id),
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    symbol       TEXT,                   -- NULL for cash sweep rows
    description  TEXT,
    quantity     REAL,
    price        REAL,
    market_value REAL NOT NULL
);
```

Column additions to existing tables:

```sql
-- accounts
asset_class       TEXT CHECK(asset_class IN ('stocks','cash','retirement','other')),
external_ref      TEXT,    -- institution account number (last 4 ok) to auto-route holdings CSVs
flip_amount_signs INTEGER NOT NULL DEFAULT 0,

-- net_worth_snapshots
source TEXT NOT NULL DEFAULT 'manual'   -- 'manual' | 'sheet' | 'holdings_csv'
```

New config (`.env` / `config.py`):

```
LIVE_START_MONTH=2026-06   # months >= this come from transactions; earlier from monthly_summaries
```

### Canonical category list (seed `categories` table)
Match the sheet so history and go-forward data pivot identically:

| name | kind | notes |
|---|---|---|
| Rent + Utilities | expense | |
| Home | expense | |
| Groceries | expense | |
| Food | expense | restaurants/delivery (sheet calls dining "Food") |
| Clothes | expense | |
| Entertainment | expense | |
| Fitness | expense | |
| Donations | expense | |
| Misc | expense | |
| Travel | expense | |
| Car | expense | gas, insurance, parking, tolls |
| Health | expense | new — sheet folded into Misc |
| Paycheck | income | |
| RSU Vest | income | |
| Interest | income | |
| Other Income | income | |
| Transfers | transfer | CC payments, Venmo in/out, internal moves |
| Investments | investment | transfers INTO brokerage; drives FCF |

Rewrite the seed rules in `services/rules.py` to target these categories (current rules use Dining/Transport/Subscriptions/etc. — remap: Dining→Food, Transport→Car or Travel, Subscriptions→Entertainment or Misc, Rent/Housing→Rent + Utilities, Utilities→Rent + Utilities, Healthcare→Health, Personal Care→Misc, Shopping→Home or Clothes or Misc as judged, Fees→Misc, Income→Paycheck).

---

## 5. Unified aggregation layer (the keystone)

One module, e.g. `models/aggregates.py`, is the only place dashboards read cashflow from:

```
monthly_cashflow(start_month, end_month) -> rows of (month, category, kind, amount)
```

- For months `< LIVE_START_MONTH`: `SELECT month, category, kind, amount FROM monthly_summaries WHERE source='sheet'`.
- For months `>= LIVE_START_MONTH`: aggregate `transactions` joined to `categories`:
  - expense rows: `SUM(-amount)` where `amount < 0` and kind='expense'
  - income rows: `SUM(amount)` where `amount > 0` and kind='income'
  - investment rows: `SUM(ABS(amount))` where kind='investment'
  - transfers excluded entirely.
- Derived metrics computed in Python from those rows: total income, total expenses, expenses-as-%-of-income, net income, FCF (net − investments), cumulative net income, per-category % of income.

Same idea for net worth — it's simpler because bootstrap and go-forward both write to the SAME tables (`net_worth_snapshots` + `snapshot_account_balances`); the time series just works. Asset-class rollup = join balances → accounts.asset_class.

If a net-new CSV happens to contain a few pre-cutover transactions, they are stored (dedup keeps re-uploads safe) but the dashboard ignores them — sheet data is authoritative before `LIVE_START_MONTH`.

---

## 6. Implementation phases

Each phase is independently shippable. Acceptance criteria included so progress is verifiable without context.

### Phase 0 — Foundations & bug fixes (small) — ✅ DONE 2026-06-09
- [x] Fix the 5 bugs in §3.
- [x] Apply schema changes from §4; update `schema.sql`; delete `data/finance.db` (contains only test data — confirmed 2026-06-09); re-init on next run.
- [x] Seed `categories` table; load categories from DB everywhere `config.CATEGORIES` was used.
- [x] Remap and seed `rules` table from `services/rules.py`; `apply_rules()` now reads active rules from DB ordered by priority.
- [x] Accounts UI: add asset_class, external_ref, flip_amount_signs fields.

**Done when:** app boots clean from empty DB; uploading the same CSV twice yields 0 duplicates; categories page of review UI shows new category list. *(All verified by live upload tests — Citi debit/credit format, Amex flip format, duplicate re-upload, no-API-key flash, review page category options.)*

**Additional findings fixed during implementation:**
- Debit/credit CSVs with empty cells crashed the parser (pandas NaN is truthy, so the `or "0"` fallback never fired) — empty cells now coalesce to 0 and all-empty rows are skipped.
- Citi reports payments as *negative* values in the Credit column; amount formula is now `abs(credit) − abs(debit)`, which handles both Citi's and the conventional convention. With this fix Citi needs **no** flip_amount_signs; the flag is for single-Amount-column issuers that report charges as positive (e.g. Amex).
- This Mac has no `python` alias (use `python3`) and macOS AirPlay Receiver squats on port 5000 answering 403s — `PORT` is now configurable via `.env` (set `PORT=5001`).
- Note: `rules.pattern` matching is substring-based; seeded 18 categories + 253 rules.

### Phase 1 — Bootstrap from the Google Sheet — ✅ DONE 2026-06-09

**Outcome:** 629 monthly_summaries rows (2020–2026), 74 monthly snapshots (2020-05-31 →
2026-06-30), 1,060 card transactions (Apr 2025–Apr 2026), 12 accounts. Implemented in
`scripts/bootstrap_from_sheet.py` (`make bootstrap` / `make bootstrap-reset`).

**Findings vs. the original plan (the real workbook at `data/bootstrap/expenses.xlsx` was
richer than the Drive pull suggested):**
- Tabs are named `Budget 2020`…`Budget 2026` (history goes back to May 2020, not 2022).
- A `Transactions` tab holds 1,063 card-level rows (Apr 2025+, columns: Date, Purchase,
  Price, Category, Split, Notes, Final Cost, Amount Owed, Source). Imported as real
  transactions (`import_batch_id='sheet-bootstrap'`, account "Card (sheet import)",
  amount = −Final Cost, i.e. Sri's share after splits). They're card-only (no rent/income),
  so Budget aggregates stay authoritative pre-cutover; `LIVE_START_MONTH=2026-05`
  (cashflow data ends 2026-04; balances end 2026-06).
- Old-tab quirks handled: 2020 splits Rent/Utilities (merged), "Misc." → Misc,
  "Running /Cycling/Fitness" → Fitness, "C1 Interest" → Interest, Paycheck 1+2 summed,
  "Unvested RSUs" junk row skipped, "Cumulative Assets" (2020) read as the NW row.
  Account renames mapped to one continuous account: TDAmeritrade → "TDAmeritrade / Schwab"
  → "Schwab - personal"; "CitiBank CDs" → CDs; "CaptialOne" typo fixed.
- Validation caught **the sheet's own formula bugs** (import is correct, sheet was wrong):
  2022 Jun–Sep Net Worth SUM excluded the newly added Vanguard row (under-stated by up to
  $5,000); 2023 Sep/Nov/Dec Total Expenses excluded the Car row.
- Unparsed tabs (deliberately): `NW` (quarterly rollup — derived data), `Income`, `Goals`,
  `Owed Summary` (splits live in-app), `CDs`, `Treasuries`, `Donations`, and `Vanguard`
  (holdings detail — possibly useful reference for Phase 4).

Original checklist:
- [x] User action: download the Google Sheet as `.xlsx` into `data/bootstrap/` (arrived as `expenses.xlsx`).
- [x] `scripts/bootstrap_from_sheet.py` (openpyxl, already a dependency):
  - Iterate tabs whose name parses as a year (verify actual tab names at implementation time; keep a `TAB_YEAR_OVERRIDES` dict for odd names).
  - Locate blocks by anchor text in column A/B (`Income`, `Expenses`, `Total Assets`, `Net Worth`), then read month columns Jan–Dec to the right. Robust to blocks moving between years. Skip bill-split and recurring mini-tables.
  - Income rows → `monthly_summaries` kind='income' (normalize: "Paycheck 1"/"Paycheck 2" → sum into `Paycheck`; "Post Tax RSU Vest" → `RSU Vest`; interest rows → `Interest`; "Other Income" → `Other Income`).
  - Expense rows → kind='expense' (normalize "Running /Cycling/Fitness"→`Fitness`, "Misc."→`Misc`).
  - Net Income block: only the `Investments` row → kind='investment'. All other rows are derived; recompute, don't import.
  - Total Assets grid → create accounts on first sight (normalized names + asset_class per §2.7 mapping; fix the "CaptialOne" typo) and one snapshot per month-end (`source='sheet'`, date = last day of month) with per-account balances. Skip empty cells (account didn't exist yet).
  - Cross-check: recompute each month's net worth from imported balances and compare to the sheet's own `Net Worth` row; print discrepancies > $50. Same for Total Income / Total Expenses vs imported line items.
  - Idempotent: `--reset` flag deletes `monthly_summaries WHERE source='sheet'` and snapshots `WHERE source='sheet'` (cascade balances) before re-import.
- [x] Set `LIVE_START_MONTH` to the first month NOT fully covered by the sheet → `2026-05` (cashflow data ends April 2026).
- [x] A raw markdown pull of the sheet (taken 2026-06-09 via Drive connector) is saved at `data/bootstrap/sheet_raw_pull_2026-06-09.md` — use it to validate parsed numbers if the xlsx is ambiguous, and for unit-test fixtures.

**Done when:** script prints per-year row counts + validation summary with no discrepancies; `net_worth_snapshots` holds ~4–5 years of monthly snapshots; spot-check three known values from the raw pull (e.g. Net Worth May 2026 = $500,000, Total Expenses Apr 2026 = $5,000). *(Verified: NW 2026-05-31 = 792,233.71, NW 2026-06-30 = 828,116.54, first snapshot 2020-05-31 = 8,269.80; the only discrepancies are documented sheet-formula bugs above.)*

### Phase 2 — Dashboard pages — ✅ DONE 2026-06-09
- [x] `GET /dashboard` (now the app home): year selector; income vs expenses bars + net
  income line; sheet-parity pivots (Income, Expenses with Year + % of income columns,
  Net Income block with Expenses-%, Investments, FCF, Cumulative); stat cards.
- [x] Net worth page upgrade: stat cards (current / vs-last-month / vs-last-year),
  stacked asset-class chart (full 2020→now history), account × month grid per year with
  per-class subtotal rows, snapshot form prefilled with last-known balances.
- [x] All reads go through `models/aggregates.py` (cashflow) + `models/net_worth.py` (NW).

**Verified:** /dashboard?year=2025 shows Income $500,000 / Expenses $50,000 — matches the
sheet's 2025 tab exactly; NW page shows current $500,000 MoM +$50,000; the 2024 grid
includes the closed Etrade account. Number formatting is whole-dollar in tables.

**Pulled forward from Phase 3 (Sri requested it for adding new banks):** every upload now
goes through a **preview step** — nothing inserts until confirmed. The preview shows parsed
sample rows with sign coloring, lets you remap columns via dropdowns (for banks whose
headers auto-detection misses) and toggle sign-flip, then "remember these settings" persists
to a new `accounts.csv_mapping` JSON column (+ flip flag) so future uploads parse
automatically. Added `database/db.py _migrate()` for additive ALTERs now that the DB holds
real data (wipe-and-reseed is no longer acceptable). Verified end-to-end with a fake bank
CSV (`Posting Day,Details,Value`, charges positive): detect-fail → manual map → flip →
import (correct signs/categories) → saved mapping auto-applied on re-upload → dedup held.

### Phase 3 — Rules registry UI + import hardening — ✅ DONE 2026-06-09
- [x] `GET/POST /rules` page: list, add/edit/delete/toggle; "Test against history" dry-runs a
  pattern over all transactions (count + 8 samples) before saving. Regexes validated on save.
- [x] "Re-apply rules" action: re-categorizes transactions whose `category_source` is
  `rule`/`claude`/NULL; NEVER overwrites `user`-sourced.
- [x] Review UI: "+ Rule" button per transaction (prefills pattern/category on /rules).

**Verified on real data:** re-apply categorized 9 of the 31 uncategorized bootstrap rows
(31 → 22) while the 1,029 user-sourced rows stayed byte-identical — including UBER rows Sri
had deliberately filed as Travel/Entertainment rather than Car, and Apple charges filed as
Fitness (Apple Fitness+). Creating "valencia farm" → Groceries via the form + re-apply
categorized the matching bootstrap row with `source='rule'`.

**Finding:** Apple's card descriptor truncates to `APPLE.COM/BILINTERNET CHARGE`, so the
seeded pattern "apple.com/bill" missed and the "internet" rule (Rent + Utilities) caught it.
Seed pattern is now `apple.com/bil` (rules.py + live DB). General lesson for rule-writing:
test patterns against history — card descriptors get truncated mid-word.
- [x] Upload preview step (see §3 bug 3): parse → show table with computed signs/categories → confirm → insert. Sign-flip toggle persists to the account. *(Done early with Phase 2, including per-account column-mapping persistence in `accounts.csv_mapping`.)*

**Done when:** a Citi CSV imports with correct signs end-to-end; creating a rule from review and re-applying categorizes look-alike transactions; user-corrected categories survive re-apply.

**Real-statement shakedown (2026-06-10):** imported Sri's actual May 1 – Jun 10 statements —
Citi checking (24 rows), Citi Double Cash (30), Amex (132; flip_amount_signs=1). Fixes that
came out of it (now in csv_parser.py):
- Citi checking dates use dashes (`06-09-2026`) → added `%m-%d-%Y` to `_parse_date`.
- Citi checking rows end with a trailing comma → without `index_col=False`, pandas silently
  shifts every column left (date lands in Status). Now passed always.
- Amex multi-line quoted fields parse fine; Amex "Description" can repeat (multiple UBER
  rows/day) — dedup key includes amount, so only identical same-day same-amount rows collapse.
- Card descriptors truncate mid-word; rules must target the stable prefix
  ("doordas", "valencia whol", "apple.com/bil").
- Statements of ANY length/overlap are fine: dedup is the DB UNIQUE constraint, re-uploads
  skip existing rows (verified).
- Added 21 merchant/pattern rules from the real data (tst* → Food, american expr ach pmt /
  payment - thank you → Transfers, mr liquor → Groceries, google *webpass → Rent + Utilities,
  anthropic → Misc, etc.) — coverage on the 186 new rows: 88% by rules, 23 left for review.
- Validation: Transfers across the 3 files net to exactly $50 (card payments cancel
  between checking and card sides — no double counting). May 2026 dashboard now renders
  from live transactions (cutover working): income $5,000 expenses $5,000.

### Phase 4a — Brokerage holdings via CSV upload — ✅ DONE 2026-06-09

> Decision history: Plaid was considered and **rejected the same day** (Sri: no paid
> services — Plaid's free Development env is gone, Investments is a paid product).
> CSVs are the primary path; files stay local in `data/uploads/`. For direct pulls,
> see Phase 4b (free Schwab official API).

- [x] `services/holdings_parser.py`: format autodetection + parsers for
  **Schwab Positions export** (multi-account sections, "Cash & Cash Investments" → symbol
  NULL, "Account Total" used for validation only) and **Vanguard download-center CSV**
  (holdings section parsed, transactions section ignored, settlement fund → cash).
  Built against documented formats; synthetic-file tests pass with totals matching the
  files' own Account Total rows. **First real files may drift — the preview will show it;
  adjust the parser then.**
- [x] Upload card on /net-worth → `POST /net-worth/holdings/preview` (nothing saved) →
  per-section: account picker (auto-matched via `accounts.external_ref` last-4, with
  "remember account number" option), positions table, computed-vs-file total check →
  `POST /net-worth/holdings/confirm`.
- [x] Snapshot **upsert** semantics (`nw_model.upsert_snapshot`): Schwab upload, Vanguard
  upload, and the manual prefilled form all **merge into the same dated snapshot** —
  verified: 2 uploads + manual CitiBank entry on one date produced 1 snapshot, 3 balances,
  correct total; re-importing the same file replaces holdings instead of duplicating.
- [x] Holdings/allocation table on /net-worth: latest snapshot's positions aggregated by
  ticker across accounts (Schwab personal + ExampleCo + Vanguard combined), % of holdings.

**Real-file shakedown (2026-06-10):** imported Sri's actual Schwab exports — "Schwab @0"
(personal, 23 positions) and "Designated Bene Individual @0" (the ExampleCo RSU account,
281 EXMP + cash). Parser fixes from real files: total row is **"Positions Total"** (not
"Account Total"), the type column is **"Asset Type"** (not "Security Type"), and we now
capture **asset_type + cost_basis** per holding (new columns via `_migrate()`).
**Brokerage cash classification** (Sri's requirement): holdings rows with
asset_type='cash' (sweep + money market like SWVXX — $50k of it in Schwab personal!) are
reclassified from the account's class into Cash in the class chart and the year-grid
subtotals. Chart/grid now use the latest snapshot **per month**, so a mid-month positions
upload doesn't fake a dip. Both files' computed totals matched the files' own Positions
Total to the cent.

**TODO (Sri, 2026-06-10): rule engine for holdings** — ✅ shipped same day in its simplest
useful form: per-symbol asset-type overrides (`holding_overrides` table), set via a Class
dropdown on each /net-worth/equities row, applied at read time across ALL snapshots
(grouping, cash reclassification in the NW chart/grid, everything goes through
`models/net_worth.py`). "(reset)" option reverts to the file's/API's classification.
Pattern-based rules (regex over description, region tags) remain a future idea if
per-symbol ever isn't enough.

### Phases 5.5 — Life tab, income summary, equities page — ✅ DONE 2026-06-10 (Sri's asks)
- [x] **/life**: declared fixed/needed monthly spend (`life_items` table) with stat cards:
  needed/mo, base-pay/mo (YTD avg of Paycheck months), needed as % of base pay, avg actual
  spend/mo, discretionary/mo. Seeded from the sheet's recurring-expenses list ($5,000/mo
  incl. rent 4,095). CRUD + active toggle.
- [x] **Base Pay YTD** stat card on /dashboard (Paycheck income line only, excludes RSU/other).
- [x] **/net-worth/equities**: latest positions aggregated by ticker across accounts, grouped
  Stocks/ETFs/Mutual Funds/Cash, with qty, value, % of invested, cost basis, gain $/%
  (where the file provides basis — Vanguard doesn't), plus a concentration warning
  (currently: EXMP = 43% of invested, flagged extra because employer == ExampleCo).
  This is the seed of the Phase 6 investment critic.
- [x] Inline category override on /transactions (AJAX select per row, saves as user-sourced).

### Phase 4b — Direct Schwab pull via the official (free) Schwab API — 🔶 BUILT 2026-06-10, awaiting Sri's developer-app approval

**Target workflow (Sri, 2026-06-10):** only upload CitiBank/CapitalOne checking + Amex/Citi
card CSVs; everything brokerage syncs via API.

**Implemented** (`services/schwab_api.py`, `schwab_tokens` table, routes
`/net-worth/schwab/exchange` + `/net-worth/schwab/sync`, UI card on /net-worth):
- OAuth via paste-the-redirect-URL flow (no local HTTPS listener): authorize link →
  Schwab login → lands on `https://127.0.0.1/?code=…` browser error page → paste full URL
  within ~30s. Access tokens auto-refresh; refresh tokens last **7 days** → UI shows
  days-left and flips back to connect mode on expiry.
- Sync maps `/trader/v1/accounts?fields=positions` into the SAME sections shape as the CSV
  parser and writes through `upsert_snapshot` + `replace_holdings`. Asset types mapped
  (CASH_EQUIVALENT→cash, COLLECTIVE_INVESTMENT→etf…), sweep cash added from
  `currentBalances.cashBalance`, cost basis = averagePrice × qty. Account matching reuses
  `external_ref` (983 / 401 already saved). `map_account()` is pure — unit-tested against a
  synthetic payload; values matched the real CSV import within rounding.
- **Cannot be end-to-end tested until Sri's app is approved**: register at
  developer.schwab.com (product "Accounts and Trading Production", callback exactly
  `https://127.0.0.1`), wait for "Ready for use", set `SCHWAB_APP_KEY`/`SECRET` in `.env`.

**Hard limits confirmed (told to Sri):** the Trader API returns actual Schwab accounts
only — **linked external accounts (his Vanguard) are NOT included** (stays CSV/manual),
and **unvested RSUs are NOT exposed** (Equity Award Center has no public API). The
Equities page shows vested shares + post-tax RSU vest income YTD ($50,000 in 2026)
instead; upcoming-vest tracking would need a manual vest-schedule table (future idea).

**Done when (4b):** "Sync Schwab" pulls real positions into today's snapshot with no file involved.

### Phase 5 — Polish — ✅ DONE 2026-06-10
- [x] Recurring-expense detection (`services/recurring.py`): normalized merchant
  (lowercase, strip `*…`/digits/punct, first 24 chars), ≥3 occurrences, median gap
  23–37 days, every amount within ±15% of the median → "Recurring Expenses (detected)"
  table on /dashboard with monthly total. On real data it found Webpass, Google One,
  Netflix, Uber One, Lemonade (+ a monthly restaurant habit — working as specified).
  Links to /life for comparison against declared needed spend.
- [x] Exporters refreshed. Excel adds 3 sheets: `Cashflow YYYY` (sheet-parity pivot:
  income/expense rows × months + Net Income block), `NW by Class` (monthly class series +
  line chart), `Assets YYYY` (account×month grid + class subtotals). HTML export rebuilt
  on `models/aggregates` + `models/net_worth`: stat cards, stacked NW-by-class chart,
  income-vs-expenses chart, category bars, account×month table — and **Chart.js is now
  embedded inline** (vendored at `static/js/chart.umd.min.js`), zero CDN references,
  works fully offline.
- [x] ~~`.gitignore` covering `data/`, `.env`, `.venv/`~~ — superseded 2026-06-10: Sri
  decided this repo will **never** go to git (real financial data), so `.gitignore` was
  removed entirely. Do not `git init` here.

### Phase 5.6 — RSU vest log — ✅ DONE 2026-06-10 (Sri: "the equities tab isn't properly getting my vest information — the current approach doesn't handle the May vest")
**Root cause:** vests never appear in checking/card CSVs (shares land at Schwab), and the
sheet's "Post Tax RSU Vest" row only covers pre-cutover months — so any vest in a live
month (≥ LIVE_START_MONTH) was missing from income/net income/FCF entirely.
- [x] "Log vest" form on /net-worth/equities (`POST /net-worth/equities/vest`): date,
  post-tax $, optional shares, symbol (default EXMP), account (defaults to Schwab - ExampleCo).
  Saves a normal `RSU Vest` income **transaction** (source='user') → flows through
  `models/aggregates` into the dashboard month automatically. Dedup via the transactions
  UNIQUE constraint (same date+description+amount logs once).
- [x] Vest history table on the same card: sheet monthly aggregates (pre-cutover) +
  logged vest transactions (post-cutover), via `aggregates.vest_history()`.
- [ ] **Sri action:** log the May 2026 vest (post-tax $ + share count) — and each future
  vest on vest day. If the Schwab API ever exposes EAC transfers, auto-detect then.

### Phase 6 — Future / not now
- **Investment critic** (Sri's idea, 2026-06-09): analysis layer over the `holdings` table —
  concentration risk (e.g. EXMP position + RSU exposure at the employer that pays the
  paychecks = double concentration), allocation drift vs a target, fund overlap (VTI vs
  VTSAX both = US total market), cash drag, expense-ratio audit. Could be rule-based first,
  Claude-powered commentary later. Needs fresh holdings → motivates Phase 4b.
- Aggregators if free options die: SimpleFIN Bridge (~$50/mo). Plaid rejected (cost).
- iCloud-folder HTML export for phone viewing (set `OUTPUT_FOLDER` to an iCloud Drive path).

---

## 7. Decisions log

| Decision | Rationale |
|---|---|
| History = monthly aggregates, not synthetic transactions | Sri won't backfill CSVs; faking transactions would pollute the transaction table and dedup logic |
| `LIVE_START_MONTH` hard cutover, sheet wins before it | Simple, explicit, no double-counting; partial pre-cutover CSV data ignored by dashboards |
| Categories renamed to match the sheet | Historical and live data must pivot in one table; sheet names are the canon |
| Rules in DB, not code | User asked for an editable "registry"; seed from existing rules.py |
| Snapshots (not holdings) remain the NW source of truth | Mixed manual + CSV accounts; holdings are enrichment attached to snapshots |
| Wipe DB instead of migrations | DB has only test data (verified 2026-06-09) |
