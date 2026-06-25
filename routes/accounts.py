from flask import Blueprint, render_template, request, redirect, url_for, flash
import models.account as account_model
import config
from services import plaid_api

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
def index():
    import models.net_worth as nw_model
    accounts = account_model.get_all()
    balances = nw_model.get_latest_balances()
    net = sum(-b if a["is_liability"] else b
              for a in accounts for b in [balances.get(a["id"])] if b is not None)
    plaid_on = plaid_api.configured()
    return render_template("accounts/index.html", accounts=accounts,
                           balances=balances, net=net,
                           plaid_configured=plaid_on,
                           plaid_items=plaid_api.status() if plaid_on else [],
                           plaid_env=config.PLAID_ENV)


def _optional_fields(form):
    return {
        "asset_class":       form.get("asset_class") or None,
        "external_ref":      form.get("external_ref", "").strip() or None,
        "flip_amount_signs": 1 if form.get("flip_amount_signs") else 0,
    }


@bp.route("/", methods=["POST"])
def create():
    name        = request.form["name"].strip()
    type_       = request.form["type"]
    institution = request.form.get("institution", "").strip()
    is_liability = 1 if type_ in ("credit", "loan") else 0
    account_model.create(name, type_, institution, is_liability=is_liability,
                         **_optional_fields(request.form))
    flash(f'Account "{name}" created.')
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/edit", methods=["POST"])
def edit(account_id):
    account_model.update(
        account_id,
        request.form["name"].strip(),
        request.form["type"],
        request.form.get("institution", "").strip(),
        **_optional_fields(request.form),
    )
    flash("Account updated.")
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/delete", methods=["POST"])
def delete(account_id):
    try:
        account_model.delete(account_id)
        flash("Account deleted.")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("accounts.index"))
