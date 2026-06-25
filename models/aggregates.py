"""
Unified read layer for dashboards (docs/PRD.md §5).

Cashflow months before config.LIVE_START_MONTH come from `monthly_summaries`
(bootstrapped sheet history); months from it onward are aggregated live from
`transactions`. Dashboards must read through here, never both tables directly.
"""

import config
from database.db import get_db
import models.category as category_model

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def available_years():
    db = get_db()
    years = {int(r[0]) for r in db.execute(
        "SELECT DISTINCT substr(month, 1, 4) FROM monthly_summaries")}
    years |= {int(r[0]) for r in db.execute(
        "SELECT DISTINCT strftime('%Y', date) FROM transactions "
        "WHERE strftime('%Y-%m', date) >= ?", (config.LIVE_START_MONTH,))}
    return sorted(years)


def monthly_cashflow(year):
    """Rows of (month 'YYYY-MM', category, kind, amount>0) for one year."""
    db = get_db()
    cutover = config.LIVE_START_MONTH
    sheet = db.execute(
        "SELECT month, category, kind, amount FROM monthly_summaries "
        "WHERE month LIKE ? AND month < ? AND source='sheet'",
        (f"{year}-%", cutover)).fetchall()
    # True spend (PRD-2 Phase 7): COALESCE(my_share, amount) — when a charge is
    # split with friends, only my share counts as expense. Income/investment rows
    # never have my_share set.
    live = db.execute(
        """SELECT strftime('%Y-%m', t.date) AS month, t.category AS category, c.kind AS kind,
                  SUM(CASE WHEN c.kind = 'income' THEN t.amount
                           ELSE -COALESCE(t.my_share, t.amount) END) AS amount
           FROM transactions t JOIN categories c ON c.name = t.category
           WHERE c.kind IN ('expense', 'income', 'investment')
             AND strftime('%Y', t.date) = ? AND strftime('%Y-%m', t.date) >= ?
           GROUP BY month, t.category, c.kind""",
        (str(year), cutover)).fetchall()
    return [dict(r) for r in sheet] + [dict(r) for r in live]


def vest_history():
    """Every RSU vest on record, oldest first: monthly sheet aggregates before the
    cutover, individual vest transactions (logged on /net-worth/equities) after."""
    db = get_db()
    cutover = config.LIVE_START_MONTH
    sheet = db.execute(
        """SELECT month AS date, NULL AS id, 'sheet' AS source,
                  'monthly total (sheet bootstrap)' AS description, amount
           FROM monthly_summaries
           WHERE category='RSU Vest' AND month < ? AND source='sheet'""",
        (cutover,)).fetchall()
    live = db.execute(
        """SELECT date, id, 'logged' AS source, description, amount
           FROM transactions
           WHERE category='RSU Vest' AND strftime('%Y-%m', date) >= ?""",
        (cutover,)).fetchall()
    return sorted([dict(r) for r in sheet] + [dict(r) for r in live],
                  key=lambda r: r["date"])


def build_year_dashboard(year):
    """Everything the /dashboard template needs for one year, sheet-style:
    income rows, expense rows (with year totals and % of income), and the
    Net Income block (net, investments, FCF, cumulative)."""
    rows = monthly_cashflow(year)

    by_kind = {"income": {}, "expense": {}, "investment": {}}
    for r in rows:
        m = int(r["month"][5:7])
        cell = by_kind[r["kind"]].setdefault(r["category"], [0.0] * 12)
        cell[m - 1] += r["amount"]

    def ordered(kind):
        canon = [c["name"] for c in category_model.get_by_kind(kind)]
        present = by_kind[kind]
        names = [n for n in canon if n in present]
        names += sorted(n for n in present if n not in canon)  # uncanonical leftovers
        return [{"name": n, "by_month": present[n], "total": sum(present[n])} for n in names]

    income_rows, expense_rows = ordered("income"), ordered("expense")

    income_total = [sum(r["by_month"][m] for r in income_rows) for m in range(12)]
    expense_total = [sum(r["by_month"][m] for r in expense_rows) for m in range(12)]
    invest = [0.0] * 12
    for cat_months in by_kind["investment"].values():
        invest = [a + b for a, b in zip(invest, cat_months)]

    net = [i - e for i, e in zip(income_total, expense_total)]
    fcf = [n - v for n, v in zip(net, invest)]
    pct = [(e / i if i else None) for i, e in zip(income_total, expense_total)]
    cum, run = [], 0.0
    for n in net:
        run += n
        cum.append(run)

    yr_income, yr_expense = sum(income_total), sum(expense_total)
    for r in expense_rows:
        r["pct_income"] = (r["total"] / yr_income) if yr_income else None

    return {
        "year": year,
        "years": available_years(),
        "months": MONTH_NAMES,
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "income_total": income_total,
        "expense_total": expense_total,
        "pct": pct,
        "net": net,
        "investments": invest,
        "fcf": fcf,
        "cumulative": cum,
        "ytd": {
            "income": yr_income,
            "expenses": yr_expense,
            "net": yr_income - yr_expense,
            "investments": sum(invest),
            "fcf": yr_income - yr_expense - sum(invest),
            "savings_rate": ((yr_income - yr_expense) / yr_income) if yr_income else None,
        },
    }
