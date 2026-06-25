from database.db import get_db

def get_all_snapshots():
    return get_db().execute(
        "SELECT * FROM net_worth_snapshots ORDER BY snapshot_date DESC"
    ).fetchall()

def get_snapshot_with_balances(snapshot_id):
    snapshot = get_db().execute(
        "SELECT * FROM net_worth_snapshots WHERE id=?", (snapshot_id,)
    ).fetchone()
    balances = get_db().execute(
        """SELECT sab.*, a.name as account_name, a.type as account_type
           FROM snapshot_account_balances sab
           JOIN accounts a ON sab.account_id=a.id
           WHERE sab.snapshot_id=?""",
        (snapshot_id,),
    ).fetchall()
    return snapshot, balances

def create_snapshot(snapshot_date, account_balances, notes=""):
    return upsert_snapshot(snapshot_date, account_balances, notes, source="manual")


def upsert_snapshot(snapshot_date, account_balances, notes="", source="manual"):
    """
    account_balances: list of (account_id, balance) tuples.
    If a snapshot already exists for snapshot_date, the given accounts' balances
    are replaced within it (other accounts untouched) — so a Schwab holdings
    upload, a Vanguard upload, and the manual form can all contribute to one
    snapshot. Totals are recomputed from ALL balances on the snapshot.
    """
    db = get_db()
    existing = db.execute(
        "SELECT id, notes, source FROM net_worth_snapshots WHERE snapshot_date=? "
        "ORDER BY id LIMIT 1", (snapshot_date,)).fetchone()

    if existing:
        snapshot_id = existing["id"]
        for account_id, _ in account_balances:
            db.execute("DELETE FROM snapshot_account_balances WHERE snapshot_id=? AND account_id=?",
                       (snapshot_id, account_id))
    else:
        cur = db.execute(
            "INSERT INTO net_worth_snapshots (snapshot_date, total_assets, total_liabilities, "
            "net_worth, notes, source) VALUES (?,0,0,0,?,?)",
            (snapshot_date, notes, source))
        snapshot_id = cur.lastrowid

    for account_id, balance in account_balances:
        db.execute(
            "INSERT INTO snapshot_account_balances (snapshot_id, account_id, balance) VALUES (?,?,?)",
            (snapshot_id, account_id, balance),
        )

    totals = db.execute(
        """SELECT COALESCE(SUM(CASE WHEN a.is_liability THEN 0 ELSE b.balance END), 0) AS assets,
                  COALESCE(SUM(CASE WHEN a.is_liability THEN ABS(b.balance) ELSE 0 END), 0) AS liabilities
           FROM snapshot_account_balances b JOIN accounts a ON a.id = b.account_id
           WHERE b.snapshot_id=?""", (snapshot_id,)).fetchone()
    new_source = "holdings_csv" if source == "holdings_csv" else (existing["source"] if existing else source)
    db.execute(
        "UPDATE net_worth_snapshots SET total_assets=?, total_liabilities=?, net_worth=?, source=? WHERE id=?",
        (totals["assets"], totals["liabilities"], totals["assets"] - totals["liabilities"],
         new_source, snapshot_id))
    db.commit()
    return snapshot_id


def replace_holdings(snapshot_id, account_id, positions):
    """Idempotent: re-importing the same file replaces that account's holdings."""
    db = get_db()
    db.execute("DELETE FROM holdings WHERE snapshot_id=? AND account_id=?",
               (snapshot_id, account_id))
    for p in positions:
        db.execute(
            """INSERT INTO holdings (snapshot_id, account_id, symbol, description, quantity,
                                     price, market_value, asset_type, cost_basis)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (snapshot_id, account_id, p["symbol"], p["description"], p["quantity"],
             p["price"], p["market_value"], p.get("asset_type"), p.get("cost_basis")))
    db.commit()


def _holdings_cash():
    """(snapshot_id, account_id) -> cash+money-market value inside that account's
    holdings. Used to move brokerage cash from the Stocks class into Cash.
    Respects per-symbol holding_overrides."""
    rows = get_db().execute(
        """SELECT h.snapshot_id, h.account_id, SUM(h.market_value) AS cash
           FROM holdings h LEFT JOIN holding_overrides o ON o.symbol = h.symbol
           WHERE COALESCE(o.asset_type, h.asset_type) = 'cash'
           GROUP BY h.snapshot_id, h.account_id""").fetchall()
    return {(r["snapshot_id"], r["account_id"]): r["cash"] for r in rows}


def set_holding_override(symbol, asset_type):
    """asset_type=None/'' clears the override (back to the file's classification)."""
    db = get_db()
    if asset_type:
        db.execute(
            "INSERT INTO holding_overrides (symbol, asset_type) VALUES (?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET asset_type=excluded.asset_type",
            (symbol, asset_type))
    else:
        db.execute("DELETE FROM holding_overrides WHERE symbol=?", (symbol,))
    db.commit()


def get_latest_holdings():
    """EACH ACCOUNT's most recent holdings, combined and aggregated by symbol.
    Per-account (not one global snapshot) because sources land on different
    dates — e.g. a Schwab sync today + last month-end's Vanguard statement.
    Returns (newest_date, rows) — rows sorted by value desc."""
    db = get_db()
    latest = db.execute(
        """SELECT account_id, snapshot_id, snapshot_date FROM (
             SELECT h.account_id, h.snapshot_id, s.snapshot_date,
                    ROW_NUMBER() OVER (PARTITION BY h.account_id
                                       ORDER BY s.snapshot_date DESC, s.id DESC) AS rn
             FROM (SELECT DISTINCT account_id, snapshot_id FROM holdings) h
             JOIN net_worth_snapshots s ON s.id = h.snapshot_id)
           WHERE rn = 1""").fetchall()
    if not latest:
        return None, []
    pairs = [(r["snapshot_id"], r["account_id"]) for r in latest]
    cond = " OR ".join("(h.snapshot_id=? AND h.account_id=?)" for _ in pairs)
    params = [v for p in pairs for v in p]
    rows = db.execute(
        f"""SELECT COALESCE(h.symbol, 'CASH') AS symbol,
                  MIN(h.description) AS description,
                  SUM(h.quantity) AS quantity,
                  SUM(h.market_value) AS value,
                  COALESCE(MAX(o.asset_type), MAX(h.asset_type)) AS asset_type,
                  MAX(o.asset_type) IS NOT NULL AS overridden,
                  SUM(h.cost_basis) AS cost_basis,
                  MIN(h.cost_basis) IS NULL AS basis_incomplete,
                  GROUP_CONCAT(DISTINCT a.name) AS accounts
           FROM holdings h JOIN accounts a ON a.id = h.account_id
                LEFT JOIN holding_overrides o ON o.symbol = h.symbol
           WHERE {cond}
           GROUP BY COALESCE(h.symbol, 'CASH')
           ORDER BY value DESC""", params).fetchall()
    return max(r["snapshot_date"] for r in latest), rows

def get_timeseries():
    return get_db().execute(
        "SELECT snapshot_date, net_worth, total_assets, total_liabilities FROM net_worth_snapshots ORDER BY snapshot_date ASC"
    ).fetchall()

CLASS_ORDER = ["stocks", "cash", "retirement", "other"]

def get_class_series():
    """Net worth split by asset class over time, one point per month (the LATEST
    snapshot in each month, so a partial mid-month holdings upload doesn't show as
    a dip). Cash/money-market held inside brokerage holdings is reclassified from
    the account's class into 'cash'."""
    db = get_db()
    snaps = db.execute(
        "SELECT id, snapshot_date FROM net_worth_snapshots ORDER BY snapshot_date, id"
    ).fetchall()
    latest = {}  # 'YYYY-MM' -> (id, date); later rows win
    for s in snaps:
        latest[s["snapshot_date"][:7]] = (s["id"], s["snapshot_date"])
    if not latest:
        return [], {c: [] for c in CLASS_ORDER}

    ids = [sid for sid, _ in latest.values()]
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"""SELECT b.snapshot_id, b.account_id, b.balance,
                   COALESCE(a.asset_class, 'other') AS cls, a.is_liability
            FROM snapshot_account_balances b JOIN accounts a ON a.id = b.account_id
            WHERE b.snapshot_id IN ({placeholders})""", ids).fetchall()
    cash_map = _holdings_cash()

    by_id = {}  # snapshot_id -> {cls: total}
    for r in rows:
        totals = by_id.setdefault(r["snapshot_id"], {c: 0.0 for c in CLASS_ORDER})
        signed = -r["balance"] if r["is_liability"] else r["balance"]
        cls = r["cls"] if r["cls"] in CLASS_ORDER else "other"
        held_cash = cash_map.get((r["snapshot_id"], r["account_id"]), 0.0)
        if cls != "cash" and held_cash:
            totals["cash"] += held_cash
            totals[cls] += signed - held_cash
        else:
            totals[cls] += signed

    dates, series = [], {c: [] for c in CLASS_ORDER}
    for month in sorted(latest):
        sid, date_str = latest[month]
        dates.append(date_str)
        for c in CLASS_ORDER:
            series[c].append(round(by_id.get(sid, {}).get(c, 0.0), 2))
    return dates, series

def snapshot_years():
    return [int(r[0]) for r in get_db().execute(
        "SELECT DISTINCT substr(snapshot_date, 1, 4) FROM net_worth_snapshots ORDER BY 1")]

def get_year_grid(year):
    """The sheet's 'Total Assets' view: accounts × months for one year, using the
    latest snapshot in each month. Accounts ordered by asset class, then name."""
    db = get_db()
    snaps = db.execute(
        "SELECT id, snapshot_date FROM net_worth_snapshots WHERE snapshot_date LIKE ? "
        "ORDER BY snapshot_date, id", (f"{year}-%",)).fetchall()
    latest = {}  # month idx -> snapshot id (later rows win)
    for s in snaps:
        latest[int(s["snapshot_date"][5:7])] = s["id"]
    if not latest:
        return {"months": [], "accounts": [], "net_worth": {}, "class_totals": {}}

    placeholders = ",".join("?" * len(latest))
    snap_to_month = {sid: m for m, sid in latest.items()}
    rows = db.execute(
        f"""SELECT b.snapshot_id, b.balance, b.account_id, a.name, a.asset_class, a.is_liability
            FROM snapshot_account_balances b JOIN accounts a ON a.id = b.account_id
            WHERE b.snapshot_id IN ({placeholders})""", list(latest.values())).fetchall()
    cash_map = _holdings_cash()

    accounts = {}
    net_worth, class_totals = {}, {}
    for r in rows:
        m = snap_to_month[r["snapshot_id"]]
        acct = accounts.setdefault(r["name"], {
            "name": r["name"], "asset_class": r["asset_class"], "by_month": {}})
        signed = -r["balance"] if r["is_liability"] else r["balance"]
        acct["by_month"][m] = r["balance"]
        net_worth[m] = net_worth.get(m, 0.0) + signed
        cls = r["asset_class"] or "other"
        # Brokerage-held cash counts toward the Cash class subtotal
        held_cash = cash_map.get((r["snapshot_id"], r["account_id"]), 0.0)
        if cls != "cash" and held_cash:
            class_totals.setdefault("cash", {})[m] = class_totals.get("cash", {}).get(m, 0.0) + held_cash
            signed -= held_cash
        class_totals.setdefault(cls, {})[m] = class_totals.get(cls, {}).get(m, 0.0) + signed

    rank = {c: i for i, c in enumerate(CLASS_ORDER)}
    ordered = sorted(accounts.values(),
                     key=lambda a: (rank.get(a["asset_class"], 99), a["name"]))
    return {"months": sorted(latest), "accounts": ordered,
            "net_worth": net_worth, "class_totals": class_totals}

def get_latest_balances():
    """account_id -> most recent recorded balance (prefills the snapshot form)."""
    rows = get_db().execute(
        """SELECT b.account_id, b.balance,
                  ROW_NUMBER() OVER (PARTITION BY b.account_id
                                     ORDER BY s.snapshot_date DESC, s.id DESC) AS rn
           FROM snapshot_account_balances b
           JOIN net_worth_snapshots s ON s.id = b.snapshot_id"""
    ).fetchall()
    return {r["account_id"]: r["balance"] for r in rows if r["rn"] == 1}
