from database.db import get_db


def bulk_insert(rows):
    """rows: dicts with account_id/date/settle_date/symbol/type/quantity/price/
    fees/amount/source/raw. INSERT OR IGNORE — statement re-imports are no-ops."""
    db = get_db()
    inserted = 0
    for r in rows:
        cur = db.execute(
            """INSERT OR IGNORE INTO investment_transactions
               (account_id, date, settle_date, symbol, type, quantity, price,
                fees, amount, source, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            # symbol '' (not NULL) for cash rows: SQLite UNIQUE treats NULLs as
            # distinct, which would defeat re-import dedup for deposits.
            (r["account_id"], r["date"], r.get("settle_date"), r.get("symbol") or "",
             r["type"], r.get("quantity"), r.get("price"), r.get("fees"),
             r["amount"], r["source"], r.get("raw")))
        inserted += cur.rowcount
    db.commit()
    return inserted


def get_all(account_id=None, symbol=None, year=None, type_=None):
    q = ("SELECT it.*, a.name AS account_name FROM investment_transactions it "
         "JOIN accounts a ON a.id = it.account_id WHERE 1=1")
    params = []
    if account_id:
        q += " AND it.account_id=?"; params.append(account_id)
    if symbol:
        q += " AND it.symbol=?"; params.append(symbol)
    if year:
        q += " AND strftime('%Y', it.date)=?"; params.append(str(year))
    if type_:
        q += " AND it.type=?"; params.append(type_)
    q += " ORDER BY it.date DESC, it.id DESC"
    return get_db().execute(q, params).fetchall()


def income_ytd(year):
    """Dividends/interest/capital gains received this year, from the ledger."""
    rows = get_db().execute(
        """SELECT type, SUM(amount) AS total FROM investment_transactions
           WHERE strftime('%Y', date)=? AND type IN
                 ('dividend','interest','capgain_st','capgain_lt')
           GROUP BY type""", (str(year),)).fetchall()
    return {r["type"]: r["total"] for r in rows}


def monthly_deposits(year):
    """month 'YYYY-MM' -> net deposits into brokerages (for reconciliation
    against the cashflow 'Investments' row)."""
    rows = get_db().execute(
        """SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
           FROM investment_transactions
           WHERE type IN ('deposit','withdrawal') AND strftime('%Y', date)=?
           GROUP BY month""", (str(year),)).fetchall()
    return {r["month"]: r["total"] for r in rows}
