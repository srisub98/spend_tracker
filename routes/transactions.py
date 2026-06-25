import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import models.transaction as tx_model
import models.account as account_model
import models.category as category_model
from services.csv_parser import parse_csv, read_headers
from services.categorizer import categorize_transactions
from services.rules import suggest_pattern
from services.storage import upload_path

MAPPING_KEYS = ("date", "desc", "amount", "debit", "credit", "type")

bp = Blueprint("transactions", __name__, url_prefix="/transactions")
PAGE_SIZE = 50


@bp.route("/")
def index():
    page        = int(request.args.get("page", 1))
    account_id  = request.args.get("account_id") or None
    category    = request.args.get("category") or None
    start_date  = request.args.get("start_date") or None
    end_date    = request.args.get("end_date") or None
    status      = request.args.get("status") or None

    txs   = tx_model.get_all(account_id, category, start_date, end_date, PAGE_SIZE, (page - 1) * PAGE_SIZE, status=status)
    total = tx_model.count(account_id, category, start_date, end_date, status=status)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    review_count = tx_model.count(account_id, category, start_date, end_date, status="review")

    accounts   = account_model.get_all()
    categories = category_model.get_names()
    return render_template(
        "transactions/index.html",
        transactions=txs, accounts=accounts, categories=categories,
        page=page, pages=pages, total=total, review_count=review_count,
        filters=dict(account_id=account_id, category=category, start_date=start_date, end_date=end_date, status=status),
    )


def _form_mapping(form):
    """Column mapping from the preview form's dropdowns; None if all blank."""
    mapping = {k: form.get(f"map_{k}") or None for k in MAPPING_KEYS}
    return mapping if any(mapping.values()) else None


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    """GET: upload form. POST: parse and show a PREVIEW — nothing is inserted
    until the user confirms. Re-posted from the preview itself to try a
    different column mapping (new banks: upload an example CSV, adjust the
    mapping until the sample parses right, then confirm + save mapping)."""
    accounts = account_model.get_all()
    if request.method == "GET":
        return render_template("transactions/upload.html", accounts=accounts)

    account_id = request.form.get("account_id")
    file = request.files.get("csv_file")

    # Resolve the filename first; the on-disk path needs the account's provider.
    if file and file.filename:
        filename = secure_filename(file.filename) or "upload.csv"
    else:
        filename = secure_filename(request.form.get("filename", ""))  # re-preview

    if not filename or not account_id:
        flash("Please select a file and an account.", "error")
        return render_template("transactions/upload.html", accounts=accounts)

    account = account_model.get_by_id(int(account_id))
    save_path = upload_path(filename, account=account)  # data/uploads/<provider>/
    if file and file.filename:
        file.save(save_path)

    # First preview uses the account's saved settings; re-previews (posted from
    # the preview page, marked by map_* fields) use exactly what the form says.
    is_repreview = "map_date" in request.form
    mapping = _form_mapping(request.form)
    if not is_repreview and mapping is None and account["csv_mapping"]:
        mapping = json.loads(account["csv_mapping"])
    flip = bool(request.form.get("flip")) if is_repreview else bool(account["flip_amount_signs"])

    try:
        rows, stats = parse_csv(save_path, int(account_id), flip_signs=flip, mapping=mapping)
        error = None
    except ValueError as e:
        rows, stats, error = [], {"headers": read_headers(save_path), "columns": mapping or {},
                                  "total": 0, "rule_matched": 0, "unmatched": 0, "skipped": 0}, str(e)
    except Exception as e:
        flash(f"Could not read CSV: {e}", "error")
        return render_template("transactions/upload.html", accounts=accounts)

    return render_template(
        "transactions/preview.html",
        account=account, filename=filename, error=error,
        sample=rows[:20], stats=stats, flip=flip,
        mapping_keys=MAPPING_KEYS,
    )


@bp.route("/upload/confirm", methods=["POST"])
def upload_confirm():
    """Insert the previewed file using the confirmed mapping/sign settings,
    optionally persisting them to the account for future uploads."""
    account_id = int(request.form["account_id"])
    filename   = secure_filename(request.form["filename"])
    account    = account_model.get_by_id(account_id)
    save_path  = upload_path(filename, account=account)

    mapping = _form_mapping(request.form)
    flip    = bool(request.form.get("flip"))

    try:
        rows, stats = parse_csv(save_path, account_id, flip_signs=flip, mapping=mapping)
    except ValueError as e:
        flash(f"Parse error: {e}", "error")
        return redirect(url_for("transactions.upload"))

    if request.form.get("save_mapping"):
        account_model.update_csv_settings(account_id, mapping, flip)

    inserted = tx_model.bulk_insert(rows)

    # Only freshly inserted rows that no rule matched go to Claude;
    # querying by batch_id avoids mismatching rows with duplicate descriptions.
    unmatched = tx_model.get_uncategorized_by_batch(stats["batch_id"])
    pairs, errors = categorize_transactions(unmatched)
    if pairs:
        tx_model.bulk_update_category(pairs, source="claude")
    for err in errors:
        flash(err, "error")

    flash(
        f"Imported {inserted} new transactions "
        f"({stats['rule_matched']} auto-categorized by rules, "
        f"{len(pairs)} categorized by Claude, "
        f"{stats['total'] - inserted} duplicates skipped)."
    )
    return redirect(url_for("transactions.review"))


@bp.route("/review")
def review():
    txs        = tx_model.get_uncategorized()
    categories = category_model.get_names()
    return render_template("transactions/review.html", transactions=txs, categories=categories)


@bp.route("/bulk-category", methods=["POST"])
def bulk_category():
    """Mass-categorize selected transactions (e.g. all from the Needs Review
    view), then suggest a rule pattern shared across them so future imports
    of the same merchant categorize automatically."""
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    category = request.form.get("category") or None

    return_args = {k: v for k, v in {
        "page": request.form.get("page"),
        "status": request.form.get("status"),
        "account_id": request.form.get("account_id"),
        "category": request.form.get("filter_category"),
        "start_date": request.form.get("start_date"),
        "end_date": request.form.get("end_date"),
    }.items() if v}

    if not ids or category not in category_model.get_names():
        flash("Select at least one transaction and a valid category.", "error")
        return redirect(url_for("transactions.index", **return_args))

    descs = tx_model.get_descriptions(ids)
    tx_model.bulk_set_category(ids, category)
    flash(f"Updated {len(ids)} transaction(s) to {category}.")

    pattern = suggest_pattern(descs)
    if pattern:
        return_args["suggest_pattern"] = pattern
        return_args["suggest_category"] = category
    return redirect(url_for("transactions.index", **return_args))


@bp.route("/<int:transaction_id>/category", methods=["POST"])
def update_category(transaction_id):
    category = (request.form.get("category") or
                (request.json.get("category") if request.is_json else None)) or None
    tx_model.update_category(transaction_id, category, source="user")
    if request.is_json:
        return jsonify(ok=True)
    return redirect(url_for("transactions.review"))


@bp.route("/<int:transaction_id>/delete", methods=["POST"])
def delete(transaction_id):
    tx_model.delete(transaction_id)
    flash("Transaction deleted.")
    return redirect(url_for("transactions.index"))


@bp.route("/<int:transaction_id>/split", methods=["POST"])
def split(transaction_id):
    """True spend (PRD-2 Phase 7): split a card charge with friends. The
    dashboard then counts only my share; friends' shares become receivables."""
    import models.bill_split as split_model
    tx = tx_model.get_by_id(transaction_id)
    if not tx or tx["amount"] >= 0:
        flash("Only expense transactions can be split.", "error")
        return redirect(url_for("transactions.index"))
    if tx["my_share"] is not None:
        flash("Already split — unsplit it first.", "error")
        return redirect(url_for("transactions.index"))

    names = [n.strip() for n in request.form.get("names", "").split(",") if n.strip()]
    if not names:
        flash("Give at least one name to split with.", "error")
        return redirect(url_for("transactions.index"))

    total = abs(tx["amount"])
    custom = request.form.get("shares", "").strip()
    if custom:
        try:
            shares = [round(float(s), 2) for s in custom.split(",")]
        except ValueError:
            flash("Custom shares must be comma-separated numbers.", "error")
            return redirect(url_for("transactions.index"))
        if len(shares) != len(names):
            flash(f"{len(names)} names but {len(shares)} share amounts.", "error")
            return redirect(url_for("transactions.index"))
    else:
        equal = round(total / (len(names) + 1), 2)
        shares = [equal] * len(names)
    if sum(shares) >= total:
        flash("Friends' shares exceed the whole charge — check the amounts.", "error")
        return redirect(url_for("transactions.index"))

    outing_id = split_model.split_transaction(tx, list(zip(names, shares)))
    my_part = total - sum(shares)
    flash(f"Split: you ${my_part:,.2f}, " +
          ", ".join(f"{n} ${s:,.2f}" for n, s in zip(names, shares)) +
          f". Dashboard now counts only your share; track settlement on the Splits page.")
    return redirect(request.referrer or url_for("transactions.index"))


@bp.route("/<int:transaction_id>/unsplit", methods=["POST"])
def unsplit(transaction_id):
    import models.bill_split as split_model
    split_model.unsplit_transaction(transaction_id)
    flash("Split removed — the full charge counts as your expense again.")
    return redirect(request.referrer or url_for("transactions.index"))
