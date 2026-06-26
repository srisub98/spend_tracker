import re
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import config
import models.net_worth as nw_model
import models.account as account_model
from services.holdings_parser import parse_holdings
from services.storage import upload_path
from services import schwab_api
from services.schwab_api import SchwabAuthError

bp = Blueprint("net_worth", __name__, url_prefix="/net-worth")


def _digits(s):
    return re.sub(r"\D", "", s or "")


def _match_account(account_ref, accounts):
    """Match a parsed account ref to a local account via external_ref (last-4 style)."""
    ref = _digits(account_ref)
    for a in accounts:
        ext = _digits(a["external_ref"])
        if ext and ref and len(ext) >= 3 and (ref.endswith(ext) or ext.endswith(ref)):
            return a["id"]
    return None


@bp.route("/")
def index():
    years = nw_model.snapshot_years()
    default_year = date.today().year if date.today().year in years else (years[-1] if years else date.today().year)
    year = int(request.args.get("year", default_year))

    snapshots = nw_model.get_all_snapshots()
    dates, class_series = nw_model.get_class_series()

    # MoM / YoY: compare latest snapshot to ~1 and ~12 snapshots back (monthly cadence)
    series = list(reversed(nw_model.get_timeseries()))  # newest first
    current = series[0]["net_worth"] if series else None
    mom = (current - series[1]["net_worth"]) if len(series) > 1 else None
    yoy = (current - series[12]["net_worth"]) if len(series) > 12 else None
    mom_pct = (mom / series[1]["net_worth"]) if mom is not None and series[1]["net_worth"] else None
    yoy_pct = (yoy / series[12]["net_worth"]) if yoy is not None and series[12]["net_worth"] else None
    nw_spark = [round(r["net_worth"]) for r in reversed(series[:13])]  # last ~13, oldest first

    holdings_date, holdings = nw_model.get_latest_holdings()
    holdings_total = sum(r["value"] for r in holdings)

    import models.bill_split as split_model
    return render_template(
        "net_worth/index.html",
        receivable=split_model.total_receivable(),
        schwab_configured=schwab_api.configured(),
        schwab_status=schwab_api.status() if schwab_api.configured() else None,
        schwab_auth_url=schwab_api.auth_url() if schwab_api.configured() else None,
        snapshots=snapshots,
        accounts=account_model.get_all(),
        today=date.today().isoformat(),
        year=year, years=years,
        grid=nw_model.get_year_grid(year),
        chart_dates=dates, class_series=class_series,
        current=current, mom=mom, yoy=yoy,
        mom_pct=mom_pct, yoy_pct=yoy_pct, nw_spark=nw_spark,
        latest_balances=nw_model.get_latest_balances(),
        class_order=nw_model.CLASS_ORDER,
        holdings=holdings, holdings_date=holdings_date, holdings_total=holdings_total,
    )


@bp.route("/equities")
def equities():
    """Moved to /investments (PRD-2 Phase 9) — keep the old URL working."""
    return redirect(url_for("investments.index"))


@bp.route("/equities/vest", methods=["POST"])
def log_vest():
    """Record an RSU vest as an income transaction (category 'RSU Vest') so live
    months get vest income — vests never appear in checking/card CSVs."""
    import models.transaction as tx_model
    try:
        amount = float(request.form["amount"])
        vest_date = request.form["vest_date"]
        account_id = int(request.form["account_id"])
    except (ValueError, KeyError):
        flash("Vest needs a date, account, and post-tax dollar amount.", "error")
        return redirect(url_for("net_worth.equities"))
    if amount <= 0:
        flash("Vest amount should be positive (post-tax value of the shares).", "error")
        return redirect(url_for("net_worth.equities"))

    symbol = (request.form.get("symbol") or config.EMPLOYER_STOCK_SYMBOL).strip().upper()
    shares = (request.form.get("shares") or "").strip()
    desc = (f"{symbol} " if symbol else "") + "RSU vest" + \
        (f" — {shares} shares" if shares else "") + " (post-tax)"
    inserted = tx_model.bulk_insert([{
        "account_id": account_id, "date": vest_date, "description": desc,
        "amount": amount, "category": "RSU Vest", "category_source": "user",
    }])
    if inserted:
        flash(f"Vest logged: {desc}, ${amount:,.2f} on {vest_date}. "
              "Dashboard income/FCF for that month now includes it.")
    else:
        flash("That exact vest (same date, description, amount) is already logged.", "error")
    return redirect(url_for("net_worth.equities"))


@bp.route("/equities/classify", methods=["POST"])
def classify_holding():
    """Per-symbol asset-type override from the Equities page (holdings 'rule engine')."""
    symbol = request.form.get("symbol", "").strip()
    asset_type = request.form.get("asset_type", "").strip() or None
    if not symbol:
        return jsonify({"ok": False, "error": "missing symbol"}), 400
    if asset_type and asset_type not in ("equity", "etf", "mutual_fund", "cash", "other"):
        return jsonify({"ok": False, "error": "bad asset_type"}), 400
    nw_model.set_holding_override(symbol, asset_type)
    return jsonify({"ok": True})


@bp.route("/schwab/exchange", methods=["POST"])
def schwab_exchange():
    """Finish the OAuth flow: user pastes the https://127.0.0.1/?code=... URL."""
    try:
        schwab_api.exchange_redirect_url(request.form.get("redirect_url", ""))
        flash("Schwab connected. Tokens last 7 days — use Sync anytime until then.")
    except SchwabAuthError as e:
        flash(str(e), "error")
    return redirect(url_for("net_worth.index"))


@bp.route("/schwab/sync", methods=["POST"])
def schwab_sync():
    """Pull balances + positions for all Schwab accounts into today's snapshot —
    same write path as a holdings CSV upload."""
    try:
        sections = schwab_api.fetch_sections()
    except SchwabAuthError as e:
        flash(str(e), "error")
        return redirect(url_for("net_worth.index"))
    except Exception as e:
        flash(f"Schwab sync failed: {e.__class__.__name__}: {e}", "error")
        return redirect(url_for("net_worth.index"))

    accounts = account_model.get_all()
    snapshot_date = date.today().isoformat()
    imported, unmatched = [], []
    for s in sections:
        account_id = _match_account(s["account_ref"], accounts)
        if not account_id:
            unmatched.append(s["account_ref"][-4:])
            continue
        total = s["total"] if s["total"] is not None else sum(
            p["market_value"] for p in s["positions"])
        snapshot_id = nw_model.upsert_snapshot(
            snapshot_date, [(account_id, total)],
            notes="schwab api sync", source="holdings_csv")
        nw_model.replace_holdings(snapshot_id, account_id, s["positions"])
        acct = account_model.get_by_id(account_id)
        imported.append(f"{acct['name']} (${total:,.0f}, {len(s['positions'])} positions)")

    if imported:
        flash(f"Schwab synced into the {snapshot_date} snapshot: {'; '.join(imported)}.")
    if unmatched:
        flash("No local account matched Schwab account(s) ending " + ", ".join(unmatched) +
              " — set that as the account # on the Accounts page and sync again.", "error")
    return redirect(url_for("net_worth.index"))


@bp.route("/statement/preview", methods=["POST"])
def statement_preview():
    """Vanguard monthly statement PDF (PRD-2 Phase 8): preview holdings with
    cost basis + parsed trades/deposits before writing anything."""
    from services.vanguard_pdf import parse_statement, VanguardParseError
    file = request.files.get("statement_file")
    if not file or not file.filename:
        flash("Pick a statement PDF first.", "error")
        return redirect(url_for("net_worth.index"))

    filename = secure_filename(file.filename) or "statement.pdf"
    save_path = upload_path(filename, bucket="statements")
    file.save(save_path)

    try:
        stmt = parse_statement(save_path)
    except VanguardParseError as e:
        flash(str(e), "error")
        return redirect(url_for("net_worth.index"))

    accounts = account_model.get_all()
    matched = _match_account(stmt["account_ref"] or "", accounts)
    return render_template(
        "net_worth/statement_preview.html",
        stmt=stmt, filename=filename, accounts=accounts,
        matched_account_id=matched,
    )


@bp.route("/statement/confirm", methods=["POST"])
def statement_confirm():
    from services.vanguard_pdf import parse_statement, VanguardParseError
    import models.investment as inv_model
    filename = secure_filename(request.form["filename"])
    account_id = int(request.form["account_id"])
    save_path = upload_path(filename, bucket="statements")

    try:
        stmt = parse_statement(save_path)
    except VanguardParseError as e:
        flash(f"Parse error: {e}", "error")
        return redirect(url_for("net_worth.index"))

    # (a) snapshot + holdings WITH cost basis, merged into the statement date
    snapshot_id = nw_model.upsert_snapshot(
        stmt["statement_date"], [(account_id, stmt["total_value"])],
        notes=f"vanguard statement {filename}", source="holdings_csv")
    nw_model.replace_holdings(snapshot_id, account_id, stmt["holdings"])

    # (b) trades/deposits into the investment ledger (dedup-safe)
    rows = [dict(a, account_id=account_id, source="vanguard_pdf")
            for a in stmt["activity"]]
    inserted = inv_model.bulk_insert(rows)

    if request.form.get("save_ref") and stmt["account_ref"]:
        account_model.set_external_ref(account_id, stmt["account_ref"])

    acct = account_model.get_by_id(account_id)
    flash(f"Statement imported: {acct['name']} ${stmt['total_value']:,.2f} "
          f"({len(stmt['holdings'])} holdings with cost basis) into the "
          f"{stmt['statement_date']} snapshot; {inserted} new ledger entries "
          f"({len(rows) - inserted} already imported).")
    return redirect(url_for("investments.activity"))


@bp.route("/holdings/preview", methods=["POST"])
def holdings_preview():
    file = request.files.get("holdings_file")
    if not file or not file.filename:
        flash("Pick a holdings CSV first.", "error")
        return redirect(url_for("net_worth.index"))

    filename = secure_filename(file.filename) or "holdings.csv"
    save_path = upload_path(filename, bucket="holdings")
    file.save(save_path)

    try:
        sections = parse_holdings(save_path)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("net_worth.index"))
    if not sections:
        flash("No holdings found in that file — format may have drifted; see "
              "services/holdings_parser.py.", "error")
        return redirect(url_for("net_worth.index"))

    accounts = account_model.get_all()
    for s in sections:
        s["computed_total"] = sum(p["market_value"] for p in s["positions"])
        s["matched_account_id"] = _match_account(s["account_ref"], accounts)
    return render_template(
        "net_worth/holdings_preview.html",
        sections=sections, filename=filename, accounts=accounts,
        today=date.today().isoformat(),
    )


@bp.route("/holdings/confirm", methods=["POST"])
def holdings_confirm():
    filename = secure_filename(request.form["filename"])
    snapshot_date = request.form["snapshot_date"]
    save_path = upload_path(filename, bucket="holdings")

    try:
        sections = parse_holdings(save_path)
    except ValueError as e:
        flash(f"Parse error: {e}", "error")
        return redirect(url_for("net_worth.index"))

    imported, skipped = [], 0
    for i, s in enumerate(sections):
        account_id = request.form.get(f"account_id_{i}")
        if not account_id:
            skipped += 1
            continue
        account_id = int(account_id)
        snapshot_id = nw_model.upsert_snapshot(
            snapshot_date, [(account_id, s["computed_total"] if "computed_total" in s
                             else sum(p["market_value"] for p in s["positions"]))],
            notes=f"holdings import {filename}", source="holdings_csv")
        nw_model.replace_holdings(snapshot_id, account_id, s["positions"])
        if request.form.get(f"save_ref_{i}"):
            account_model.set_external_ref(account_id, _digits(s["account_ref"])[-4:])
        acct = account_model.get_by_id(account_id)
        imported.append(f"{acct['name']} (${sum(p['market_value'] for p in s['positions']):,.0f}, "
                        f"{len(s['positions'])} positions)")

    if imported:
        flash(f"Holdings imported into the {snapshot_date} snapshot: {'; '.join(imported)}. "
              "Add balances for your remaining accounts below — same date merges into the same snapshot.")
    if skipped:
        flash(f"{skipped} account section(s) skipped (no local account selected).", "error")
    return redirect(url_for("net_worth.index"))


@bp.route("/snapshot", methods=["POST"])
def snapshot():
    snapshot_date = request.form["snapshot_date"]
    notes         = request.form.get("notes", "")
    accounts      = account_model.get_all()

    balances = []
    for acct in accounts:
        val = request.form.get(f"balance_{acct['id']}", "").strip()
        if val:
            try:
                balances.append((acct["id"], float(val)))
            except ValueError:
                pass

    if not balances:
        flash("Please enter at least one account balance.", "error")
        return redirect(url_for("net_worth.index"))

    nw_model.create_snapshot(snapshot_date, balances, notes)
    flash("Net worth snapshot saved.")
    return redirect(url_for("net_worth.index"))


@bp.route("/data")
def data():
    rows = nw_model.get_timeseries()
    return jsonify([dict(r) for r in rows])
