"""
Recurring-expense detection (PRD Phase 5): replaces the sheet's manual
recurring mini-table. A merchant is "recurring" when, after normalizing its
descriptor, it has >= 3 charges on a ~30-day cadence (median gap 23-37 days)
with amounts within ±15% of the median charge.
"""

import re
from statistics import median
from database.db import get_db

MIN_OCCURRENCES = 3
CADENCE_DAYS = (23, 37)      # ~monthly, ±~5 days plus weekend drift
AMOUNT_TOLERANCE = 0.15


def _normalize(desc):
    """Collapse a card descriptor to a stable merchant key: lowercase, strip
    store/transaction numbers, punctuation, and trailing city/state noise."""
    d = (desc or "").lower()
    d = re.sub(r"[*#]\S*", " ", d)          # APLPAY*12345, SQ #678
    d = re.sub(r"\d+", " ", d)
    d = re.sub(r"[^a-z ]", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return d[:24]


def detect():
    """Returns recurring expense candidates sorted by monthly cost desc:
    [{merchant, category, count, avg_amount, last_date, last_amount}]"""
    db = get_db()
    rows = db.execute(
        """SELECT t.date, t.description, -t.amount AS spent, t.category
           FROM transactions t
           LEFT JOIN categories c ON c.name = t.category
           WHERE t.amount < 0 AND COALESCE(c.kind, 'expense') = 'expense'
           ORDER BY t.date""").fetchall()

    groups = {}
    for r in rows:
        key = _normalize(r["description"])
        if len(key) >= 3:
            groups.setdefault(key, []).append(r)

    out = []
    for key, txs in groups.items():
        if len(txs) < MIN_OCCURRENCES:
            continue
        dates = [r["date"] for r in txs]
        gaps = [_days_between(a, b) for a, b in zip(dates, dates[1:])]
        gaps = [g for g in gaps if g > 0]    # same-day duplicates don't break cadence
        if len(gaps) < MIN_OCCURRENCES - 1:
            continue
        med_gap = median(gaps)
        if not (CADENCE_DAYS[0] <= med_gap <= CADENCE_DAYS[1]):
            continue
        amounts = [r["spent"] for r in txs]
        med_amt = median(amounts)
        if med_amt <= 0:
            continue
        if any(abs(a - med_amt) / med_amt > AMOUNT_TOLERANCE for a in amounts):
            continue
        last = txs[-1]
        out.append({
            "merchant": last["description"],
            "category": last["category"],
            "count": len(txs),
            "avg_amount": sum(amounts) / len(amounts),
            "last_date": last["date"],
            "last_amount": last["spent"],
        })
    return sorted(out, key=lambda r: -r["avg_amount"])


def _days_between(a, b):
    from datetime import date
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db_ = map(int, b.split("-"))
    return (date(yb, mb, db_) - date(ya, ma, da)).days
