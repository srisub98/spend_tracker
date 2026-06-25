"""
Spending insights & save-more (PRD-2 Phase 10): top merchants, category trends
vs your own history, subscription audit, budgets, ranked cut candidates.
"""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import get_db
import models.aggregates as agg
import models.budget as budget_model
import models.life as life_model
from services import recurring

bp = Blueprint("insights", __name__, url_prefix="/insights")


def _month_add(ym, delta):
    y, m = int(ym[:4]), int(ym[5:7])
    m += delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _category_series(months):
    """category -> {month: amount} over the given 'YYYY-MM' list (sheet + live)."""
    series = {}
    for year in sorted({int(m[:4]) for m in months}):
        for r in agg.monthly_cashflow(year):
            if r["kind"] == "expense" and r["month"] in months:
                series.setdefault(r["category"], {})[r["month"]] = \
                    series.get(r["category"], {}).get(r["month"], 0.0) + r["amount"]
    return series


def _top_merchants(limit=15):
    """True-spend top merchants over the trailing 12 months, by $ and by visits."""
    cutoff = _month_add(date.today().strftime("%Y-%m"), -12) + "-01"
    rows = get_db().execute(
        """SELECT description, category,
                  SUM(-COALESCE(my_share, amount)) AS spent, COUNT(*) AS visits
           FROM transactions WHERE amount < 0 AND date >= ?
           GROUP BY description""", (cutoff,)).fetchall()
    merged = {}
    for r in rows:
        key = recurring._normalize(r["description"])
        if len(key) < 3:
            key = (r["description"] or "?").lower()
        m = merged.setdefault(key, {"merchant": r["description"], "category": r["category"],
                                    "spent": 0.0, "visits": 0})
        m["spent"] += r["spent"]
        m["visits"] += r["visits"]
    by_spend = sorted(merged.values(), key=lambda m: -m["spent"])[:limit]
    by_visits = sorted(merged.values(), key=lambda m: -m["visits"])[:10]
    return by_spend, by_visits


@bp.route("/")
def index():
    today = date.today()
    this_month = today.strftime("%Y-%m")
    last_full = _month_add(this_month, -1)

    # --- category trends: last full month vs 3/12-month averages + YoY ---
    window = [_month_add(last_full, -i) for i in range(13)]  # last_full..-12
    series = _category_series(window + [_month_add(last_full, -12)])
    trends = []
    for cat, by_m in series.items():
        cur = by_m.get(last_full, 0.0)
        a3 = sum(by_m.get(_month_add(last_full, -i), 0.0) for i in (1, 2, 3)) / 3
        a12 = sum(by_m.get(_month_add(last_full, -i), 0.0) for i in range(1, 13)) / 12
        yoy = by_m.get(_month_add(last_full, -12))
        if cur or a12:
            trends.append({"category": cat, "current": cur, "avg3": a3, "avg12": a12,
                           "yoy": yoy, "delta12": cur - a12})
    trends.sort(key=lambda t: -abs(t["delta12"]))

    # --- budgets vs current month ---
    budget_model.seed_from_history(today.year - 1)
    budgets = budget_model.get_all()
    d = agg.build_year_dashboard(today.year)
    spent_now = {r["name"]: r["by_month"][today.month - 1] for r in d["expense_rows"]}
    budget_rows = [{"category": c, "budget": b, "spent": spent_now.get(c, 0.0)}
                   for c, b in sorted(budgets.items(), key=lambda kv: -kv[1])]

    # --- subscription audit ---
    recur = recurring.detect()
    needed = life_model.monthly_total() if hasattr(life_model, "monthly_total") else 0
    subs = []
    for r in recur:
        last_seen_age = (today - date(*map(int, r["last_date"].split("-")))).days
        subs.append(dict(r, annual=r["avg_amount"] * 12,
                         creep=r["last_amount"] > r["avg_amount"] * 1.05,
                         stale=last_seen_age > 45))
    subs.sort(key=lambda s: -s["annual"])

    # --- save-more: ranked candidates ---
    avg_spend = sum(t["avg12"] for t in trends)
    cuts = []
    for s in subs:
        if s["category"] not in ("Rent + Utilities",):
            cuts.append({"what": s["merchant"], "why": "recurring subscription",
                         "annual": s["annual"]})
    for t in trends:
        if t["delta12"] > 50:
            cuts.append({"what": t["category"],
                         "why": f"running ${t['delta12']:,.0f}/mo above your 12-mo average",
                         "annual": t["delta12"] * 12})
    cuts.sort(key=lambda c: -c["annual"])

    by_spend, by_visits = _top_merchants()
    return render_template(
        "insights/index.html",
        last_full=last_full, trends=trends[:14],
        by_spend=by_spend, by_visits=by_visits,
        budget_rows=budget_rows, month_name=today.strftime("%B"),
        subs=subs, cuts=cuts[:6],
        avg_spend=avg_spend, needed=needed,
        discretionary=avg_spend - needed,
    )


@bp.route("/budgets", methods=["POST"])
def save_budgets():
    for key, val in request.form.items():
        if key.startswith("budget_"):
            cat = key[len("budget_"):]
            val = val.strip()
            budget_model.set_budget(cat, float(val) if val else None)
    flash("Budgets saved.")
    return redirect(url_for("insights.index"))
