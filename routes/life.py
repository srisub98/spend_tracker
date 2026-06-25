from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
import models.life as life_model
import models.category as category_model
import models.account as account_model
import models.aggregates as agg

bp = Blueprint("life", __name__, url_prefix="/life")


@bp.route("/")
def index():
    items = life_model.get_all()
    needed = life_model.monthly_total()

    # Income/spend context for the current year (live + sheet via aggregates)
    year = date.today().year
    d = agg.build_year_dashboard(year)
    base_pay_ytd = next((r["total"] for r in d["income_rows"] if r["name"] == "Paycheck"), 0.0)
    months_elapsed = max(1, sum(1 for v in d["income_total"] if v > 0))
    base_pay_monthly = base_pay_ytd / months_elapsed
    # average over months that actually have spending recorded
    spend_months = [v for v in d["expense_total"] if v > 0]
    avg_spend = (sum(spend_months) / len(spend_months)) if spend_months else 0.0

    return render_template(
        "life/index.html",
        items=items, needed=needed, year=year,
        categories=category_model.get_by_kind("expense"),
        base_pay_ytd=base_pay_ytd, base_pay_monthly=base_pay_monthly,
        avg_spend=avg_spend,
        accounts=account_model.get_all(),
        today=date.today().isoformat(),
        gaps=life_model.missing_months(),
        edit_item=next((i for i in items if str(i["id"]) == request.args.get("edit", "")), None),
    )


@bp.route("/", methods=["POST"])
def create():
    name = request.form["name"].strip()
    try:
        amount = float(request.form["monthly_amount"])
    except ValueError:
        flash("Monthly amount must be a number.", "error")
        return redirect(url_for("life.index"))
    life_model.create(name, amount,
                      request.form.get("category") or None,
                      request.form.get("notes", "").strip() or None)
    flash(f'Added "{name}" (${amount:,.2f}/mo).')
    return redirect(url_for("life.index"))


@bp.route("/<int:item_id>/edit", methods=["POST"])
def edit(item_id):
    try:
        amount = float(request.form["monthly_amount"])
    except ValueError:
        flash("Monthly amount must be a number.", "error")
        return redirect(url_for("life.index", edit=item_id))
    life_model.update(item_id,
                      request.form["name"].strip(), amount,
                      request.form.get("category") or None,
                      request.form.get("notes", "").strip() or None,
                      1 if request.form.get("active") else 0)
    flash("Updated.")
    return redirect(url_for("life.index"))


@bp.route("/<int:item_id>/delete", methods=["POST"])
def delete(item_id):
    life_model.delete(item_id)
    flash("Deleted.")
    return redirect(url_for("life.index"))


@bp.route("/<int:item_id>/log", methods=["POST"])
def log_payment(item_id):
    """Log a fixed-cost item (e.g. rent paid by check/Zelle) as a transaction
    for a given month — these never appear in CSVs so the dashboard would
    otherwise undercount expenses for that month."""
    try:
        account_id = int(request.form["account_id"])
        pay_date = request.form["pay_date"]
    except (ValueError, KeyError):
        flash("Pick an account and date.", "error")
        return redirect(url_for("life.index"))

    inserted, item = life_model.log_payment(item_id, account_id, pay_date)
    if not item:
        flash("Item not found.", "error")
    elif inserted:
        flash(f'Logged "{item["name"]}" — ${item["monthly_amount"]:,.2f} on {pay_date}. '
              "It now counts toward that month's expenses.")
    else:
        flash("Already logged for that date (duplicate).", "error")
    return redirect(url_for("life.index"))
