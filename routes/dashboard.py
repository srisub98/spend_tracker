from datetime import date
from flask import Blueprint, render_template, request
import models.aggregates as agg
from services import recurring

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

QUARTER_METRICS = ("income_total", "expense_total", "net")


def _quarters(monthly):
    """[Q1, Q2, Q3, Q4] sums from a 12-value monthly list."""
    return [sum(monthly[i:i + 3]) for i in range(0, 12, 3)]


def _latest_complete_quarter(year, today):
    """0-based index of the latest quarter of `year` that has fully elapsed,
    or None if even Q1 hasn't finished yet (viewing the current year in Jan-Mar)."""
    if year < today.year:
        return 3
    if year > today.year:
        return None
    for qi in (3, 2, 1, 0):
        if qi * 3 + 3 < today.month:
            return qi
    return None


@bp.route("/")
def index():
    today = date.today()
    years = agg.available_years()
    default_year = today.year if today.year in years else (years[-1] if years else today.year)
    year = int(request.args.get("year", default_year))
    import models.budget as budget_model
    d = agg.build_year_dashboard(year)
    prev_full = agg.build_year_dashboard(year - 1) if (year - 1) in years else None
    prev = prev_full["ytd"] if prev_full else None
    budgets = budget_model.get_all()
    budget_strip = None
    if budgets and year == today.year:
        spent = {r["name"]: r["by_month"][today.month - 1] for r in d["expense_rows"]}
        budget_strip = [{"category": c, "budget": b, "spent": spent.get(c, 0.0)}
                        for c, b in sorted(budgets.items(), key=lambda kv: -kv[1])]

    quarters = None
    qi = _latest_complete_quarter(year, today)
    if qi is not None:
        qoq_src, qoq_i = (prev_full, 3) if qi == 0 else (d, qi - 1)
        quarters = {
            "n": qi + 1, "year": year,
            "qoq_n": 4 if qi == 0 else qi,
            "qoq_year": year - 1 if qi == 0 else year,
            "yoy_year": year - 1,
            "cur": {m: _quarters(d[m])[qi] for m in QUARTER_METRICS},
            "qoq": {m: _quarters(qoq_src[m])[qoq_i] for m in QUARTER_METRICS} if qoq_src else None,
            "yoy": {m: _quarters(prev_full[m])[qi] for m in QUARTER_METRICS} if prev_full else None,
        }

    return render_template("dashboard/index.html", d=d, prev=prev, quarters=quarters,
                           recurring=recurring.detect(),
                           budget_strip=budget_strip,
                           month_name=today.strftime("%B"))
