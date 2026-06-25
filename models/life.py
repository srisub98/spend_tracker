from datetime import date
from database.db import get_db
import config

def get_all(active_only=False):
    query = "SELECT * FROM life_items"
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY monthly_amount DESC, name"
    return get_db().execute(query).fetchall()

def create(name, monthly_amount, category=None, notes=None):
    db = get_db()
    cur = db.execute(
        "INSERT INTO life_items (name, monthly_amount, category, notes) VALUES (?,?,?,?)",
        (name, monthly_amount, category, notes))
    db.commit()
    return cur.lastrowid

def update(item_id, name, monthly_amount, category, notes, active):
    db = get_db()
    db.execute(
        "UPDATE life_items SET name=?, monthly_amount=?, category=?, notes=?, active=? WHERE id=?",
        (name, monthly_amount, category, notes, active, item_id))
    db.commit()

def delete(item_id):
    db = get_db()
    db.execute("DELETE FROM life_items WHERE id=?", (item_id,))
    db.commit()

def monthly_total():
    row = get_db().execute(
        "SELECT COALESCE(SUM(monthly_amount), 0) FROM life_items WHERE active=1").fetchone()
    return row[0]


def _months_since_live_start():
    """List of fully-elapsed 'YYYY-MM' months from LIVE_START_MONTH up to (not
    including) the current month — the current month is still in progress, so
    a subscription that bills later this month isn't 'missing' yet."""
    y, m = (int(p) for p in config.LIVE_START_MONTH.split("-"))
    today = date.today()
    months = []
    while (y, m) < (today.year, today.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def missing_months(active_only=True):
    """For each fixed-cost item with a category, find live months where no
    transaction matching its category + ~amount exists — i.e. the recurring
    payment never made it into a CSV (e.g. rent paid by check/Zelle).
    Amount match is a >=80% threshold rather than exact — real recurring
    costs like rent fluctuate month to month (late fees, utility true-ups)."""
    db = get_db()
    query = "SELECT * FROM life_items WHERE category IS NOT NULL"
    if active_only:
        query += " AND active=1"
    items = db.execute(query).fetchall()
    months = _months_since_live_start()
    result = []
    for item in items:
        gaps = []
        threshold = abs(item["monthly_amount"]) * 0.8
        for month in months:
            row = db.execute(
                "SELECT 1 FROM transactions WHERE date LIKE ? AND category=? "
                "AND ABS(amount) >= ? LIMIT 1",
                (f"{month}-%", item["category"], threshold),
            ).fetchone()
            if not row:
                gaps.append(month)
        if gaps:
            result.append({"item": item, "months": gaps})
    return result


def log_payment(item_id, account_id, pay_date):
    """Insert a transaction for a fixed-cost item that doesn't show up in CSVs
    (e.g. rent paid by check/Zelle) — same pattern as RSU vest logging."""
    import models.transaction as tx_model
    item = get_db().execute("SELECT * FROM life_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        return 0, None
    inserted = tx_model.bulk_insert([{
        "account_id": account_id, "date": pay_date, "description": item["name"],
        "amount": -abs(item["monthly_amount"]), "category": item["category"],
        "category_source": "user",
    }])
    return inserted, item
