from database.db import get_db


def get_all():
    return {r["category"]: r["monthly_amount"] for r in get_db().execute(
        "SELECT category, monthly_amount FROM budgets WHERE active=1").fetchall()}


def set_budget(category, monthly_amount):
    db = get_db()
    if monthly_amount is None:
        db.execute("DELETE FROM budgets WHERE category=?", (category,))
    else:
        db.execute(
            "INSERT INTO budgets (category, monthly_amount) VALUES (?,?) "
            "ON CONFLICT(category) DO UPDATE SET monthly_amount=excluded.monthly_amount",
            (category, monthly_amount))
    db.commit()


def seed_from_history(year):
    """First-run seed: each expense category's monthly average for `year`.
    Obviously editable — averages include one-offs like travel."""
    import models.aggregates as agg
    if get_all():
        return False
    rows = agg.monthly_cashflow(year)
    totals = {}
    for r in rows:
        if r["kind"] == "expense":
            totals[r["category"]] = totals.get(r["category"], 0.0) + r["amount"]
    db = get_db()
    for cat, total in totals.items():
        if total > 0:
            db.execute("INSERT OR IGNORE INTO budgets (category, monthly_amount) VALUES (?,?)",
                       (cat, round(total / 12, 0)))
    db.commit()
    return True
