"""Plaid routes (optional). The whole blueprint 404s unless Plaid is configured,
so with no PLAID_* env vars the app exposes no Plaid surface at all.

Sync mirrors transactions.upload_confirm: map → apply rules → insert (dedup-aware) →
hand the still-uncategorized rows to Claude → flash a summary.
"""
from flask import Blueprint, request, redirect, url_for, flash, jsonify, abort

import models.transaction as tx_model
import models.account as account_model
import models.plaid_item as item_model
from services import plaid_api
from services.rules import apply_rules, load_rules
from services.categorizer import categorize_transactions

bp = Blueprint("plaid", __name__, url_prefix="/plaid")


@bp.before_request
def _require_configured():
    if not plaid_api.configured():
        abort(404)


@bp.route("/link-token", methods=["POST"])
def link_token():
    """Hand the browser a fresh link_token to open Plaid Link with."""
    try:
        return jsonify(link_token=plaid_api.create_link_token())
    except Exception as e:
        return jsonify(error=f"{e.__class__.__name__}: {e}"), 500


@bp.route("/exchange", methods=["POST"])
def exchange():
    """Plaid Link's onSuccess posts the public_token here."""
    public_token = (request.get_json(silent=True) or {}).get("public_token") \
        if request.is_json else request.form.get("public_token")
    if not public_token:
        return (jsonify(error="missing public_token"), 400) if request.is_json \
            else (flash("Link did not return a token.", "error") or redirect(url_for("accounts.index")))
    try:
        plaid_api.exchange_public_token(public_token)
    except Exception as e:
        msg = f"Could not link bank: {e.__class__.__name__}: {e}"
        return (jsonify(error=msg), 500) if request.is_json else \
            (flash(msg, "error") or redirect(url_for("accounts.index")))
    if request.is_json:
        return jsonify(ok=True)
    flash("Bank linked — hit Sync to pull transactions.")
    return redirect(url_for("accounts.index"))


@bp.route("/sandbox-link", methods=["POST"])
def sandbox_link():
    """Sandbox-only convenience: link a fake bank without the Link UI, for testing."""
    try:
        plaid_api.exchange_public_token(plaid_api.sandbox_public_token())
        flash("Sandbox bank linked — hit Sync to pull its transactions.")
    except Exception as e:
        flash(f"Sandbox link failed: {e.__class__.__name__}: {e}", "error")
    return redirect(url_for("accounts.index"))


@bp.route("/sync", methods=["POST"])
def sync():
    items = item_model.get_all()
    if not items:
        flash("No linked banks yet — connect one first.", "error")
        return redirect(url_for("accounts.index"))

    rules = load_rules()
    acct_by_plaid = {a["plaid_account_id"]: a["id"]
                     for a in account_model.get_all() if a["plaid_account_id"]}

    inserted = updated = skipped = removed = 0
    new_ptids, errors = [], []
    for item in items:
        try:
            added, modified, removed_ids, cursor = plaid_api.sync_transactions(item)
        except Exception as e:
            errors.append(f"Sync failed for {item['institution'] or 'a bank'}: "
                          f"{e.__class__.__name__}: {e}")
            continue

        rows = []
        for txn in added + modified:
            acct_id = acct_by_plaid.get(txn["account_id"])
            if not acct_id:
                continue  # a Plaid account with no local mapping — skip safely
            row = plaid_api.map_transaction(txn, acct_id)
            cat = apply_rules(row["description"], rules)
            row["category"] = cat
            row["category_source"] = "rule" if cat else None
            rows.append(row)
            new_ptids.append(row["plaid_transaction_id"])

        res = tx_model.insert_plaid_rows(rows)
        inserted += res["inserted"]; updated += res["updated"]; skipped += res["skipped"]
        removed += tx_model.remove_plaid_rows(removed_ids)
        item_model.set_cursor(item["item_id"], cursor)

    # Same Claude hand-off as a CSV import, scoped to the rows we just synced.
    unmatched = tx_model.get_uncategorized_plaid_ids(new_ptids)
    pairs, cerrors = categorize_transactions(unmatched)
    if pairs:
        tx_model.bulk_update_category(pairs, source="claude")

    for e in errors + cerrors:
        flash(e, "error")
    flash(f"Plaid sync: {inserted} new, {updated} updated, "
          f"{skipped} matched existing (no duplicates), "
          f"{len(pairs)} categorized by Claude"
          + (f", {removed} removed" if removed else "") + ".")
    return redirect(url_for("accounts.index"))


@bp.route("/<item_id>/unlink", methods=["POST"])
def unlink(item_id):
    item_model.delete(item_id)
    flash("Bank unlinked. Its synced transactions are kept as history.")
    return redirect(url_for("accounts.index"))
