# PRD 2 — One-Stop Shop: True Spend, Bill Settlement, Investment Ledger, Insights

> **STATUS 2026-06-10: ALL FOUR PHASES BUILT AND VERIFIED, same day.** Sri's real May
> Vanguard statement is imported (holdings w/ basis into the 2026-05-31 snapshot, 2 buys +
> 1 deposit in the ledger, re-import verified no-op). Implementation findings:
> - **pypdf word-boundary trap**: `\b` can't match where the column header's `…2026` runs
>   into the ticker (digit→letter isn't a boundary) — symbol regex uses `(?<![A-Z])`.
> - **SQLite UNIQUE treats NULLs as distinct** — ledger dedup uses `symbol=''` for cash rows.
> - **`get_latest_holdings` is now per-account-latest** (not one global snapshot): a Schwab
>   sync today + a month-end Vanguard statement land on different dates and must combine.
> - May reconciliation shows `≠` correctly: cashflow Investments $5,000 vs ledger $5,000 —
>   the $5,000 Schwab side enters the ledger once the Schwab API app is approved (8.4).
> - Critic with both brokerages: EXMP = 33% of invested look-through (43% direct-only was
>   overstated), VFIAX+SPY duplicate-index flagged, QQQ+MGK overlap $50k, fund-fee audit.
> Remaining: 8.4 Schwab trades via API (blocked on app approval), 9.4 XIRR/Claude commentary
> (explicitly future), quarterly FUND_META refresh in services/critic.py.

**Status:** Approved plan, written 2026-06-10. Successor to `docs/PRD.md` (Phases 0–5 done,
4b built-awaiting-approval, 6 folded into Phase 9 here).
**Audience:** Any future Claude session (any model) or human picking this up cold. Read
`CLAUDE.md` for architecture and `docs/PRD.md` for everything already built. The app is in
daily use with real data — **additive migrations only** (`database/db.py _migrate()` +
`CREATE TABLE IF NOT EXISTS`), never wipe.

---

## 1. Sri's goals (2026-06-10, his words distilled)

1. **One-stop shop** for finance tracking and net worth.
2. **Settle bills** — split stuff with people, track who owes what, get paid back.
3. **Track most common categories and items**, and find **ways to save more**.
4. Same one-stop treatment for **investments**: 30,000-ft allocation view, read his
   **Vanguard statement** (PDF), understand **cost basis** and **any additional trades**.

Also: this repo will **never** be pushed to git (real financial data). `.gitignore` was
removed 2026-06-10 per Sri; there is no `.git/` directory and there never should be.

---

## 2. Gap analysis — what today's app gets wrong or doesn't do

### 2.1 The true-spend gap (the most important accounting fix in this PRD)
Sri's old sheet recorded **his share** of every card charge (the Transactions tab's
"Final Cost" column = price minus what friends owed). The app imports the **full card
charge**. So whenever he fronts a group dinner, the dashboard overstates his expenses —
and the existing bill-splits feature is a disconnected island: outings/line items have no
link to the imported transactions they correspond to, settlements don't feed anything,
and money friends owe him (the sheet's "Venmo/AppleCash" asset row) never reaches net
worth. Important corollary: **bootstrapped sheet history is already his-share**, so only
live months need fixing — no historical rewrite.

### 2.2 Investments are positions-only — no ledger, no Vanguard basis
- The Vanguard **download-center CSV has no cost basis**, so /net-worth/equities shows
  "—" for all Vanguard gains. The monthly **statement PDF has everything** (see §3).
- There is no record of **trades**: the cashflow "Investments" row tracks cash moved into
  brokerages, but not what was bought, when, at what price. Sri explicitly wants this.
- Dividends/capital-gains income (taxable! $5,000 YTD at Vanguard alone) is invisible.
- Allocation exists only as the NW class chart; there's no single "what do I own across
  Schwab + Vanguard + 401k, and what's risky" page. PRD-1 Phase 6 (critic) lands here.

### 2.3 Insights are pivot-only
The dashboard answers "how much per category per month" but not "what merchants/items do
I actually spend on", "what's trending up", "what's my budget", or "what should I cut".
The Life tab declares needed spend and recurring detection finds subscriptions, but
nothing connects them into a save-more story.

---

## 3. Data-source findings (verified 2026-06-10 against the real May 2026 statement)

### 3.1 Vanguard monthly statement PDF — the new primary Vanguard input
`statement (2).pdf`, 8 pages, account "XXXX0000" (matches `external_ref` routing).
**Text extracts cleanly with `pypdf`** (added to requirements.txt, installed in .venv).
Contents, all absent from the CSV:

| Section (page) | Data | Example from May 2026 |
|---|---|---|
| Statement overview (p2) | total value, prior-month value, asset mix | $500,000 on 05/31, $500,000 on 04/30 |
| Activity summary (p3) | deposits/withdrawals, change in value | deposits +$5,000 |
| Cost basis summary (p3) | realized ST/LT gains (month), unrealized total | unrealized $50,000 |
| YTD income (p3, p5) | dividends, interest, ST/LT cap gains | div $500, ST $500, LT $5,000 |
| Holdings (p4) | per fund: symbol, qty, price, balance (prior+current), **Total Cost Basis**, **Unrealized G/L**, EAI/EY | VFIAX 100.000 @ $500 = $50,000, basis $50,000, unrealized +$50,000 |
| Completed transactions (p5) | trade date, settle date, symbol, type, qty, price, fees, amount + ACH transfers | Buy VDIGX 10.000 @ $50 −$500; Buy VFIAX 5.000 @ $500 −$5,000; ACH from CITIBANK *0000 +$5,000 |

**Parsing strategy (prototyped):** `pypdf` returns columns run together, e.g.
`VDIGX -$500$50,000123.456$50$49,500$50,000`
(order: unrealized, basis, qty, price, prior balance, current balance). Decimal-place
patterns alone are ambiguous (a greedy price match steals digits from the next column —
confirmed in a prototype), so the parser must be **validation-driven**: enumerate the few
possible splits (price has 2–4 decimals) and accept the one where `qty × price ≈ current
balance` (±$50) and section balances sum to the account total. Same cross-check pattern
the holdings CSV parser already uses. Store the raw extracted text alongside the import
for audit/debugging, like `raw_csv_row`.

### 3.2 Schwab
- Positions CSV + (once approved) Trader API already give per-position cost basis.
- The Trader API also exposes `GET /trader/v1/accounts/{hash}/transactions` (~1-year
  lookback) — Schwab trades can flow into the same ledger (`source='schwab_api'`) once
  Sri's developer app is approved. Until then Schwab is positions-only; fine.
- Unvested RSUs remain out of reach everywhere (EAC has no API); the vest log covers it.

### 3.3 Everything else
401k / CDs / Fundrise / Coinbase / Venmo stay manual balances. For allocation purposes
they participate via `accounts.asset_class` (and §9 can show them as single blocks).

---

## 4. Schema changes (all additive)

```sql
-- Friends registry: settlement is per-person across outings, not per-outing.
CREATE TABLE IF NOT EXISTS people (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    venmo_handle TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Link split line items to the imported card transaction they came from,
-- and participants to the people registry (name kept for back-compat).
ALTER TABLE outing_line_items  ADD COLUMN transaction_id INTEGER REFERENCES transactions(id);
ALTER TABLE outing_participants ADD COLUMN person_id     INTEGER REFERENCES people(id);

-- True spend: NULL = the whole charge is mine (default). Set when a split links.
ALTER TABLE transactions ADD COLUMN my_share REAL;

-- Investment ledger: every trade / distribution / transfer at any brokerage.
CREATE TABLE IF NOT EXISTS investment_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    date        TEXT NOT NULL,             -- trade date, YYYY-MM-DD
    settle_date TEXT,
    symbol      TEXT,                      -- NULL for cash movements
    type        TEXT NOT NULL CHECK(type IN
                ('buy','sell','dividend','capgain_st','capgain_lt',
                 'interest','deposit','withdrawal','fee','other')),
    quantity    REAL,
    price       REAL,
    fees        REAL,
    amount      REAL NOT NULL,             -- signed: buys negative, deposits positive
    source      TEXT NOT NULL,             -- 'vanguard_pdf' | 'schwab_api' | 'manual'
    raw         TEXT,                      -- original parsed line (audit)
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, date, symbol, type, amount)   -- re-import safe
);

-- Per-category monthly budget targets (Phase 10).
CREATE TABLE IF NOT EXISTS budgets (
    category       TEXT PRIMARY KEY,
    monthly_amount REAL NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1
);
```

`holdings.cost_basis` already exists — the statement import simply fills it for Vanguard.

---

## 5. Phases

Each independently shippable, in recommended order. 7 and 8 are the substance; 9 and 10
compose what 7+8 store.

### Phase 7 — True spend & bill settlement
**Goal:** the dashboard shows what *Sri* spent, not what his card was charged; getting
paid back is tracked per person, not per outing.

- [ ] 7.1 `people` registry (auto-created from existing distinct participant names;
      manage on /splits). Participant forms become a person picker + free-text fallback.
- [ ] 7.2 **"Split this"** button on each /transactions row → modal/inline: pick people,
      equal split or custom amounts → creates an outing ("Dinner — MERCHANT, DATE") with
      a line item `transaction_id`-linked to the charge, participants owing their shares,
      and sets `transactions.my_share = amount + sum(others' shares)` (amount is
      negative; shares positive). Editing/deleting the split recomputes or clears
      `my_share`. Linking an existing outing line item to a transaction also possible
      from the outing detail page.
- [ ] 7.3 Aggregates use true spend: in `models/aggregates.py` live-month expense SQL,
      `COALESCE(t.my_share, t.amount)`. Sheet history needs nothing (already his share).
      The /transactions list shows both ("−$500 · your share −$50").
- [ ] 7.4 **Person ledger** page (/splits/people): per person — net owed across all
      outings, unsettled line items, history, "settle up" (marks all their unpaid
      participations paid, timestamped). Venmo handle shown for the actual request.
- [ ] 7.5 Receivables to net worth: total unsettled owed-to-me is shown on /splits and
      prefills the "Venmo/AppleCash" account line on the snapshot form (the sheet's
      convention for this exact thing).

**Done when:** splitting a real imported dinner charge drops that month's Food expense to
his share on the dashboard; the friend appears on the person ledger; settling zeroes it;
re-uploading the same statement CSV neither duplicates the transaction nor breaks the link
(dedup keeps the same row id).

### Phase 8 — Vanguard statement import + investment ledger
**Goal:** "understand my cost basis and any additional trades I have made" — upload the
monthly statement PDF, get holdings-with-basis AND a trade ledger, automatically.

- [ ] 8.1 `services/vanguard_pdf.py` (pypdf, pinned version): parse §3.1's sections with
      validation-driven number splitting (`qty × price ≈ balance` ±$50; holdings sum ≈
      account value; transactions sum ≈ deposits/withdrawals line). Returns the same
      sections shape as `holdings_parser.py` plus `activity` + `income` lists.
- [ ] 8.2 Upload card on /net-worth (next to the CSV one): preview (holdings table with
      basis, parsed trades, validation badges) → confirm writes:
      (a) `upsert_snapshot` at statement date + `replace_holdings` **with cost_basis** —
      Vanguard gains finally appear on the equities page;
      (b) `investment_transactions` rows (buys/sells/deposits/dividends), dedup-safe.
- [ ] 8.3 **/investments/activity**: filterable ledger (account, symbol, type, year).
      Reconciliation badge: monthly `deposit` totals vs the cashflow "Investments"
      category (the $5,000 ACH from Citibank should equal the May Investments row — flag
      mismatches, they mean a transfer was miscategorized on the cash side).
- [ ] 8.4 When the Schwab developer app is approved: extend `schwab_api.py` with
      `fetch_transactions()` → same table (`source='schwab_api'`), synced alongside
      positions on "Sync Schwab now".
- [ ] 8.5 Statement PDFs saved to `data/uploads/` like CSVs (audit trail).

**Done when:** importing the May 2026 statement produces exactly: 3 holdings with basis
(VDIGX $50,000 / VFIAX $50,000 / VONG $5,000), 2 buys + 1 deposit in the ledger,
a 2026-05-31 snapshot value of $500,000 merged with other accounts' balances, and
re-importing changes nothing.

### Phase 9 — 30,000-ft allocation + investment critic (absorbs PRD-1 Phase 6)
**Goal:** one page that answers *what do I own, where is it, what is it costing me, what's
risky* — across Schwab, Vanguard, 401k, everything.

- [ ] 9.1 Expand /net-worth/equities into **/investments** (nav rename; old URL redirects):
      add an allocation header — donuts/bars by asset class (manual accounts included via
      their `asset_class` as single blocks), by account, by holding type; top-10 positions
      across all brokerages with combined weight.
- [ ] 9.2 **Income view** from the ledger: YTD dividends/interest/cap-gains per account +
      taxable total (Vanguard May YTD: $5,000 — tax-relevant, he should see it grow).
- [ ] 9.3 **Critic v1 (rule-based)** — checks rendered as flagged cards with severity:
      - Concentration incl. **look-through**: EXMP direct (43% of invested!) PLUS EXMP
        inside VFIAX/VONG/QQQ — maintain a small static top-holdings map for *his* ~6
        funds (hand-maintained constants; refresh quarterly), don't build a general engine.
      - Employer double-exposure: paycheck + RSUs + index overweight all on ExampleCo.
      - Fund overlap: VFIAX ⊃ VONG (Russell 1000 Growth is a subset of S&P-ish large
        cap); quantify shared top holdings from the same static map.
      - Cash drag: brokerage cash (incl. SWVXX) as % of holdings vs a 5% guideline.
      - Expense-ratio audit: static map (VDIGX 0.29% active vs VFIAX 0.04%) → annual $.
- [ ] 9.4 Future (explicitly not now): XIRR/TWR returns from the ledger; Claude-powered
      commentary on the critic findings (he has an API key).

**Done when:** Sri opens /investments and can answer allocation, income YTD, and "what
would a sensible advisor nag me about" without opening Schwab/Vanguard.

### Phase 10 — Spending insights & save-more
**Goal:** "track my most common categories and items, and ways to save more."

- [ ] 10.1 **/insights**: top merchants by total spend and by visit count (reuse
      `recurring._normalize` for grouping), category trends (this month vs 3/6/12-month
      average and vs same month last year — sheet history gives 6 years of baseline),
      biggest movers up/down.
- [ ] 10.2 **Budgets**: per-category monthly targets (`budgets` table; seed = 2025 monthly
      average per category, editable). Dashboard gets a current-month progress strip
      (spent vs budget per category, red when over). YTD over/under on /insights.
- [ ] 10.3 **Subscription audit** on /insights: recurring detections + Life-tab items →
      annualized cost table, price-creep flags (amount up vs 6 months ago), overlap hints
      (multiple music/video subscriptions), "didn't charge last month — cancelled?" notes.
- [ ] 10.4 **Save-more report**: discretionary = avg spend − Life needed; top-3 cut
      candidates ranked by annualized savings (biggest discretionary recurring +
      trending-up categories). Optional later: Claude-generated monthly commentary.

**Done when:** "where does my money go and what should I cut" is answerable in under a
minute, with numbers (not vibes) behind every suggestion.

---

## 6. Decisions log

| Decision | Rationale |
|---|---|
| `my_share` NULL = full amount mine; only splits set it | Zero migration risk; sheet-era rows are already his-share, so history is consistent for free |
| Reinvested dividends/cap-gains do NOT enter cashflow income | Would inflate income vs the sheet's methodology (it never counted them); they live in the investment ledger + /investments income view. Bank interest stays a cashflow category |
| Statement PDF becomes the primary Vanguard input; CSV stays as fallback | PDF has basis/trades/income; CSV has none of it. Monthly statement cadence matches snapshot cadence |
| Validation-driven PDF parsing, raw text stored | pypdf run-together columns are ambiguous by regex alone (prototyped 2026-06-10); arithmetic cross-checks make it deterministic, stored raw text makes drift debuggable |
| Settlement is per-person, not per-outing | How people actually settle ("you owe me $50 total"), and matches the sheet's per-person owed summary |
| Critic uses static hand-maintained fund metadata | He holds ~6 funds; a lookup-API integration is overkill and adds a dependency for data that changes quarterly |
| Investments ledger dedup = UNIQUE(account, date, symbol, type, amount) | Same proven pattern as transactions; statement re-imports are no-ops |
| No git, ever, for this repo | Real financial data; `.gitignore` removed 2026-06-10 at Sri's request — nothing should ever `git init` here |

---

## 7. Risks & mitigations

- **PDF format drift** (Vanguard redesigns statements): validation-first parsing fails
  loudly in preview rather than importing garbage; raw text stored; parser is one file.
- **pypdf extraction order changes between versions**: pin the version in requirements.
- **Split links vs CSV dedup**: links are by transaction id; dedup keeps existing row ids
  on re-import, so links survive. Deleting a transaction must null/cascade its split link
  (handle in `transactions.delete`).
- **Static fund metadata staleness**: top-holdings %s drift; show "as of" date on the
  critic card; quarterly refresh is a 10-minute task.
- **Budget seed quality**: 2025 averages include one-offs (travel); make seeds editable
  and obvious, don't pretend precision.

---

## 8. Recommended execution order

**7 → 8 → 9 → 10.** Phase 7 fixes an active accounting error (every group dinner skews
this month's numbers), Phase 8 unlocks the data Phases 9–10 visualize. 9 before 10 only
because the investment data is fresher in mind; they're independent.
