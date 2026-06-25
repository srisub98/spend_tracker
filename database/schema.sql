CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK(type IN ('checking','savings','credit','brokerage','loan','other')),
    institution TEXT,
    currency    TEXT NOT NULL DEFAULT 'USD',
    is_liability INTEGER NOT NULL DEFAULT 0,
    -- Net-worth rollup class (sheet parity): NULL = excluded from rollup
    asset_class TEXT CHECK(asset_class IS NULL OR asset_class IN ('stocks','cash','retirement','other')),
    -- Institution account number (last 4 is enough) to auto-route holdings CSVs
    external_ref TEXT,
    -- Flip transaction amount signs on import (issuers disagree on charge sign)
    flip_amount_signs INTEGER NOT NULL DEFAULT 0,
    -- JSON column mapping for this bank's CSV format, saved from the import preview:
    -- {"date": "...", "desc": "...", "amount": "...", "debit": "...", "credit": "..."}
    csv_mapping TEXT,
    -- Plaid linkage (optional): the Plaid account_id this local account syncs from,
    -- and the owning plaid_items.item_id. NULL for CSV-only accounts.
    plaid_account_id TEXT,
    plaid_item_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    date            TEXT NOT NULL,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    category        TEXT,
    category_source TEXT CHECK(category_source IN ('rule','claude','user',NULL)),
    notes           TEXT,
    raw_csv_row     TEXT,
    import_batch_id TEXT,
    -- Plaid's stable transaction_id (NULL for CSV rows). Makes re-syncs idempotent and
    -- lets us apply Plaid 'modified'/'removed' updates by id rather than re-inserting.
    plaid_transaction_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, date, description, amount)
);

-- Canonical categories (seeded from database/seed_data.py on first init).
-- kind: expense | income | transfer | investment
--   transfer   = neutral, excluded from both spend and income
--   investment = money moved into brokerage; net income - investments = FCF
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    kind       TEXT NOT NULL CHECK(kind IN ('expense','income','transfer','investment')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1
);

-- Editable categorization rules (seeded from services/rules.py SEED_RULES on first init).
CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'substring' CHECK(match_type IN ('substring','regex')),
    category   TEXT NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 100,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Historical monthly aggregates bootstrapped from the Google Sheet (PRD §5).
-- Dashboards read these for months < LIVE_START_MONTH, transactions after.
CREATE TABLE IF NOT EXISTS monthly_summaries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    month    TEXT NOT NULL,              -- 'YYYY-MM'
    category TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK(kind IN ('expense','income','investment')),
    amount   REAL NOT NULL,              -- always positive
    source   TEXT NOT NULL DEFAULT 'sheet',
    UNIQUE(month, category, source)
);

CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date     TEXT NOT NULL,
    total_assets      REAL NOT NULL,
    total_liabilities REAL NOT NULL,
    net_worth         REAL NOT NULL,
    notes             TEXT,
    source            TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','sheet','holdings_csv')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS snapshot_account_balances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES net_worth_snapshots(id),
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    balance     REAL NOT NULL
);

-- Brokerage positions attached to a snapshot (filled by holdings CSV import, PRD Phase 4).
CREATE TABLE IF NOT EXISTS holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id  INTEGER NOT NULL REFERENCES net_worth_snapshots(id),
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    symbol       TEXT,                   -- NULL for cash sweep rows
    description  TEXT,
    quantity     REAL,
    price        REAL,
    market_value REAL NOT NULL,
    -- equity | etf | mutual_fund | cash | other — from the file's Asset/Security Type.
    -- 'cash' rows (sweep + money market like SWVXX) count as Cash, not Stocks, in rollups.
    asset_type   TEXT,
    cost_basis   REAL                    -- NULL when the file doesn't provide it (Vanguard)
);

-- Friends registry (PRD-2 Phase 7): settlement is per-person across outings.
CREATE TABLE IF NOT EXISTS people (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    venmo_handle TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Investment ledger (PRD-2 Phase 8): every trade/distribution/transfer at any brokerage.
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
    UNIQUE(account_id, date, symbol, type, amount)
);

-- Per-category monthly budget targets (PRD-2 Phase 10).
CREATE TABLE IF NOT EXISTS budgets (
    category       TEXT PRIMARY KEY,
    monthly_amount REAL NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1
);

-- Per-symbol asset-type overrides (the "rule engine for holdings" in its simplest
-- form): set from the Equities page, applied at read time over every snapshot's
-- holdings. E.g. force a bond ETF to count as 'other', or a fund to count as 'cash'.
CREATE TABLE IF NOT EXISTS holding_overrides (
    symbol     TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('equity','etf','mutual_fund','cash','other')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Schwab Trader API OAuth tokens (single row; PRD Phase 4b). Local DB only — gitignored.
CREATE TABLE IF NOT EXISTS schwab_tokens (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    access_token       TEXT,
    refresh_token      TEXT,
    access_expires_at  TEXT,    -- ISO8601; access tokens live ~30 min
    refresh_expires_at TEXT,    -- ISO8601; refresh tokens live 7 days → weekly re-login
    updated_at         TEXT
);

-- Plaid Items (one per linked institution login). Local DB only — gitignored.
-- access_token is a bearer secret; cursor drives incremental /transactions/sync.
CREATE TABLE IF NOT EXISTS plaid_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       TEXT UNIQUE NOT NULL,
    access_token  TEXT NOT NULL,
    institution   TEXT,
    cursor        TEXT,                  -- /transactions/sync cursor (NULL = full sync)
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT
);

-- "Life tab": declared fixed/needed monthly spend (rent, insurance, internet, ...).
CREATE TABLE IF NOT EXISTS life_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    monthly_amount REAL NOT NULL,
    category       TEXT,                 -- optional canonical category
    notes          TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    outing_date TEXT NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outing_participants (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    outing_id INTEGER NOT NULL REFERENCES outings(id),
    name      TEXT NOT NULL,
    is_paid   INTEGER NOT NULL DEFAULT 0,
    paid_at   TEXT
);

CREATE TABLE IF NOT EXISTS outing_line_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    outing_id         INTEGER NOT NULL REFERENCES outings(id),
    description       TEXT NOT NULL,
    total_amount      REAL NOT NULL,
    paid_by_me        INTEGER NOT NULL DEFAULT 1,
    split_count       INTEGER NOT NULL DEFAULT 2,
    per_person_amount REAL
);
