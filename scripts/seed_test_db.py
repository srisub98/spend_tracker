"""Seed a throwaway database with demo accounts for tests and local demos.

Two consumers:
  * the pytest suite imports SEED_ACCOUNTS / seed_accounts() (see tests/python/conftest.py)
  * the Playwright e2e webServer runs this directly to populate the test DB before
    the Flask app boots (see playwright.config.ts)

Honors DB_PATH from the environment, so always point it at a scratch file — never
your real database:

    DB_PATH=data/e2e_test.db python scripts/seed_test_db.py
"""
import os
import sys

# Allow running as a script (python scripts/seed_test_db.py) — put the repo root,
# not scripts/, at the front of sys.path so `import app` / `import config` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Demo accounts whose `institution` matches the providers in tests/fixtures/.
# Amex's CSV reports charges as positive, so it imports with sign-flip on; Schwab
# carries an external_ref matching schwab-positions.csv's account number.
SEED_ACCOUNTS = [
    {"name": "Citi Checking",       "type_": "checking",  "institution": "Citi"},
    {"name": "Citi Double Cash",    "type_": "credit",    "institution": "Citi"},
    {"name": "Amex Gold",           "type_": "credit",    "institution": "Amex",
     "flip_amount_signs": 1},
    {"name": "Capital One Savings", "type_": "savings",   "institution": "Capital One"},
    {"name": "Schwab Brokerage",    "type_": "brokerage", "institution": "Schwab",
     "asset_class": "stocks", "external_ref": "842"},
]


def seed_accounts():
    """Init the DB (schema + category/rule seeds) and add any missing demo
    accounts. Idempotent — safe to run repeatedly. Returns the count created."""
    from app import app
    from database.db import init_db
    import models.account as account_model

    init_db(app)
    created = 0
    with app.app_context():
        existing = {a["name"] for a in account_model.get_all()}
        for acct in SEED_ACCOUNTS:
            if acct["name"] not in existing:
                account_model.create(**acct)
                created += 1
    return created


# ---------------------------------------------------------------------------
# Rich demo dataset
# ---------------------------------------------------------------------------
# Everything below layers a *synthetic* demo dataset on top of the demo accounts
# so the dashboard, net-worth, splits, and export pages render with real content
# (and e2e/pytest report tests have something to assert on). It is intentionally
# kept OUT of seed_accounts() so the hermetic pytest suite — which assumes an
# empty transactions table — stays green. Call seed_demo_data() explicitly
# (the Playwright webServer runs `seed_test_db.py --demo`).
#
# All figures are made-up, round-ish, non-personal numbers. NEVER point this at a
# real DB. Today, for reference, is 2026-06 (config.LIVE_START_MONTH default), so:
#   * months < 2026-06 come from monthly_summaries (the "sheet" history below)
#   * June 2026 is the only "live" month, seeded as transactions
#
# The June transaction set is deliberately small (~25 rows) so it never pushes
# the upload-flow fixtures off page 1 of /transactions (PAGE_SIZE=50).

DEMO_BATCH = "demo-seed"

# (account_name, MM-DD, description, amount, category_override, source)
# amount > 0 = money in, < 0 = money out. category_override/source default to
# rule-derived; the two trailing rows simulate Claude-categorized charges that no
# rule matched, so they surface in /transactions/review.
DEMO_TRANSACTIONS = [
    # Citi Checking — income, bills, transfers, an investment contribution
    ("Citi Checking",    "06-01", "ACME CORP GUSTO PAYROLL",     8500.00, None, None),
    ("Citi Checking",    "06-15", "ACME CORP GUSTO PAYROLL",     8500.00, None, None),
    ("Citi Checking",    "06-02", "PG&E ENERGY BILL",            -180.45, None, None),
    ("Citi Checking",    "06-03", "COMCAST XFINITY INTERNET",     -89.99, None, None),
    ("Citi Checking",    "06-05", "RENT PAYMENT LANDLORD",      -2800.00, None, None),
    ("Citi Checking",    "06-10", "VANGUARD BUY ORDER",         -2000.00, None, None),
    ("Citi Checking",    "06-12", "DIVIDEND PAYMENT CHASE",        42.18, None, None),
    ("Citi Checking",    "06-20", "ZELLE TO ROOMMATE",           -650.00, None, None),
    # Capital One Savings — a little interest
    ("Capital One Savings", "06-01", "INTEREST EARNED",            18.75, None, None),
    # Citi Double Cash — everyday card spend
    ("Citi Double Cash", "06-04", "TRADER JOE'S #455",            -78.22, None, None),
    ("Citi Double Cash", "06-06", "SAFEWAY #1234",                -54.10, None, None),
    ("Citi Double Cash", "06-07", "BLUE BOTTLE COFFEE",            -6.50, None, None),
    ("Citi Double Cash", "06-08", "CHIPOTLE 2231",                -13.85, None, None),
    ("Citi Double Cash", "06-09", "NETFLIX.COM",                  -15.49, None, None),
    ("Citi Double Cash", "06-11", "SPOTIFY USA",                  -10.99, None, None),
    ("Citi Double Cash", "06-14", "CVS PHARMACY #22",             -24.30, None, None),
    ("Citi Double Cash", "06-16", "AMAZON MKTPL ORDER",           -63.47, None, None),
    ("Citi Double Cash", "06-18", "GROUP DINNER TST* NOBU",      -240.00, None, None),
    # Amex Gold — travel + car + fitness
    ("Amex Gold",        "06-05", "DELTA AIR LINES",             -342.50, None, None),
    ("Amex Gold",        "06-09", "SHELL OIL 4421",               -52.00, None, None),
    ("Amex Gold",        "06-13", "EQUINOX SF",                  -210.00, None, None),
    # Claude-categorized (no rule matches) → land in the review queue
    ("Citi Double Cash", "06-17", "QUARTERLY HOA DUES",          -125.00, "Home", "claude"),
    ("Citi Double Cash", "06-19", "LOCAL HARDWARE BARN",          -41.20, "Home", "claude"),
]

# The "group dinner" above is split 3 ways; only my third counts as true spend.
DEMO_MY_SHARE = {("Citi Double Cash", "06-18", "GROUP DINNER TST* NOBU"): -80.00}


def _summary_rows(year, months):
    """Synthetic monthly sheet aggregates. Mild month-over-month growth plus a
    deterministic wobble so the charts aren't flat. Amounts are always positive
    (the kind decides the sign downstream)."""
    rows = []
    for m in months:
        f = 1 + 0.03 * m                 # gentle growth across the year
        w = ((m * 37) % 11) / 10.0       # deterministic 0.0–1.0 wobble
        ym = f"{year}-{m:02d}"
        rows += [
            (ym, "Paycheck",         "income",     round(8500 * f, 2)),
            (ym, "Interest",         "income",     round(15 + 5 * w, 2)),
            (ym, "Rent + Utilities", "expense",    round(2800 + 100 * w, 2)),
            (ym, "Groceries",        "expense",    round(550 + 120 * w, 2)),
            (ym, "Food",             "expense",    round(420 + 150 * w, 2)),
            (ym, "Entertainment",    "expense",    round(60 + 40 * w, 2)),
            (ym, "Car",              "expense",    round(140 + 60 * w, 2)),
            (ym, "Health",           "expense",    round(40 + 50 * w, 2)),
            (ym, "Misc",             "expense",    round(90 + 80 * w, 2)),
            (ym, "Investments",      "investment", round(2000 * f, 2)),
        ]
        if m in (3, 6, 9, 12):           # quarterly RSU vests
            rows.append((ym, "RSU Vest", "income", round(12000 + 1000 * m, 2)))
        if m in (4, 7, 12):              # the occasional trip
            rows.append((ym, "Travel", "expense", round(800 + 200 * w, 2)))
    return rows


# Holdings for the latest Schwab snapshot — mirrors tests/fixtures/schwab-positions.csv
# (totals to $176,786.47, the June brokerage balance below).
DEMO_HOLDINGS = [
    {"symbol": "VTI",  "description": "VANGUARD TOTAL STOCK MARKET ETF",
     "quantity": 500, "price": 305.12, "market_value": 152560.00, "asset_type": "etf"},
    {"symbol": "AAPL", "description": "APPLE INC",
     "quantity": 100, "price": 198.40, "market_value": 19840.00, "asset_type": "equity"},
    {"symbol": None,   "description": "Cash & Cash Investments",
     "quantity": None, "price": None, "market_value": 4386.47, "asset_type": "cash"},
]


def _demo_accounts():
    """Classify the demo accounts for net-worth rollups and add a 401(k) so the
    'retirement' class is represented. Idempotent."""
    import models.account as account_model
    from database.db import get_db
    db = get_db()
    by_name = {a["name"]: a["id"] for a in account_model.get_all()}

    # asset_class drives the net-worth-by-class chart; credit cards are liabilities.
    classify = {
        "Citi Checking":       ("cash", 0),
        "Capital One Savings": ("cash", 0),
        "Schwab Brokerage":    ("stocks", 0),
        "Citi Double Cash":    (None, 1),
        "Amex Gold":           (None, 1),
    }
    for name, (cls, liab) in classify.items():
        if name in by_name:
            db.execute("UPDATE accounts SET asset_class=?, is_liability=? WHERE id=?",
                       (cls, liab, by_name[name]))
    if "Fidelity 401k" not in by_name:
        account_model.create("Fidelity 401k", "brokerage", "Fidelity",
                             asset_class="retirement")
    db.commit()


def _demo_transactions():
    """Insert the live June-2026 transactions, categorized through the real rule
    engine (so categories match production behaviour)."""
    from database.db import get_db
    from services.rules import load_rules, apply_rules
    import models.account as account_model
    db = get_db()
    if db.execute("SELECT 1 FROM transactions WHERE import_batch_id=? LIMIT 1",
                  (DEMO_BATCH,)).fetchone():
        return
    by_name = {a["name"]: a["id"] for a in account_model.get_all()}
    rules = load_rules()

    for acct, mmdd, desc, amount, override, source in DEMO_TRANSACTIONS:
        account_id = by_name.get(acct)
        if account_id is None:
            continue
        category = override or apply_rules(desc, rules)
        src = source or ("rule" if category else None)
        my_share = DEMO_MY_SHARE.get((acct, mmdd, desc))
        db.execute(
            """INSERT OR IGNORE INTO transactions
                 (account_id, date, description, amount, category, category_source,
                  my_share, import_batch_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (account_id, f"2026-{mmdd}", desc, amount, category, src, my_share, DEMO_BATCH))
    db.commit()


def _demo_monthly_summaries():
    """Bootstrapped 'sheet' history: all of 2025 plus Jan–May 2026 (everything
    before LIVE_START_MONTH). UNIQUE(month,category,source) makes this idempotent."""
    from database.db import get_db
    db = get_db()
    rows = _summary_rows(2025, range(1, 13)) + _summary_rows(2026, range(1, 6))
    db.executemany(
        "INSERT OR IGNORE INTO monthly_summaries (month, category, kind, amount, source) "
        "VALUES (?,?,?,?, 'sheet')", rows)
    db.commit()


def _demo_snapshots():
    """Monthly net-worth snapshots Jan–Jun 2026 with per-account balances, plus
    Schwab holdings on the latest one (so cash reclassification + the holdings
    table are exercised)."""
    from database.db import get_db
    import models.account as account_model
    import models.net_worth as nw_model
    db = get_db()
    if db.execute("SELECT 1 FROM net_worth_snapshots LIMIT 1").fetchone():
        return
    by_name = {a["name"]: a["id"] for a in account_model.get_all()}

    def balances(m):
        b = {
            "Citi Checking":        8000 + 800 * m,
            "Capital One Savings":  24000 + 1000 * m,
            "Schwab Brokerage":     150000 + 4000 * m,
            "Fidelity 401k":        80000 + 2000 * m,
            "Citi Double Cash":     -(1500 - 100 * m),
            "Amex Gold":            -(2500 - 150 * m),
        }
        if m == 6:                       # match the holdings total exactly
            b["Schwab Brokerage"] = 176786.47
        return [(by_name[n], v) for n, v in b.items() if n in by_name]

    last_snapshot_id = None
    for m in range(1, 7):
        last_snapshot_id = nw_model.upsert_snapshot(
            f"2026-{m:02d}-28", balances(m), notes="demo snapshot", source="manual")
    if last_snapshot_id and "Schwab Brokerage" in by_name:
        nw_model.replace_holdings(last_snapshot_id, by_name["Schwab Brokerage"],
                                  DEMO_HOLDINGS)


def _demo_outings():
    """A few bill-split outings with a mix of paid/unpaid participants, so the
    Splits page (and the Excel 'Splits Owed' sheet) show an outstanding balance."""
    from database.db import get_db
    import models.bill_split as bs
    db = get_db()
    if db.execute("SELECT 1 FROM outings LIMIT 1").fetchone():
        return

    o1 = bs.create_outing("Tahoe Ski Trip", "2026-02-15", "weekend cabin")
    bs.add_line_item(o1, "Cabin rental", 900.00, paid_by_me=1, split_count=4)
    bs.add_line_item(o1, "Groceries & gas", 320.00, paid_by_me=1, split_count=4)
    for name in ("Alex", "Jordan", "Sam"):
        bs.add_participant(o1, name)
    jordan = next(p["id"] for p in bs.get_participants(o1) if p["name"] == "Jordan")
    bs.mark_paid(jordan)

    o2 = bs.create_outing("Birthday Dinner", "2026-06-12", "")
    bs.add_line_item(o2, "Dinner @ Nobu", 480.00, paid_by_me=1, split_count=4)
    for name in ("Priya", "Maya"):
        bs.add_participant(o2, name)

    o3 = bs.create_outing("Concert Night", "2026-05-20", "")
    bs.add_line_item(o3, "Tickets", 300.00, paid_by_me=1, split_count=3)
    bs.add_participant(o3, "Chris")
    chris = next(p["id"] for p in bs.get_participants(o3) if p["name"] == "Chris")
    bs.mark_paid(chris)


def seed_demo_data():
    """Layer the full synthetic demo dataset on top of the demo accounts. Safe to
    run repeatedly on a fresh DB; each section skips itself if already populated."""
    seed_accounts()
    from app import app
    with app.app_context():
        _demo_accounts()
        _demo_transactions()
        _demo_monthly_summaries()
        _demo_snapshots()
        _demo_outings()


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    n = seed_accounts()
    target = os.environ.get("DB_PATH", "data/finance.db")
    if demo:
        seed_demo_data()
        print(f"Seeded {n} demo account(s) + full demo dataset "
              f"(transactions, sheet history, snapshots, splits) into {target}.")
    else:
        print(f"Seeded {n} demo account(s) into {target}.")
