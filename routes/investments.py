from datetime import date
from flask import Blueprint, render_template, request
import models.investment as inv_model
import models.account as account_model
import models.net_worth as nw_model
import models.aggregates as agg
from services import critic

bp = Blueprint("investments", __name__, url_prefix="/investments")


@bp.route("/")
def index():
    """The 30,000-ft view (PRD-2 Phase 9): allocation, positions with gains,
    vests, income, and the rule-based critic — across every account."""
    holdings_date, rows = nw_model.get_latest_holdings()
    year = date.today().year
    vest_ytd = sum(r["amount"] for r in agg.monthly_cashflow(year)
                   if r["category"] == "RSU Vest")
    vests = agg.vest_history()
    rows = [dict(r) for r in rows]
    total = sum(r["value"] for r in rows)
    cash = sum(r["value"] for r in rows if r["asset_type"] == "cash")
    invested = total - cash

    for r in rows:
        r["pct"] = (r["value"] / invested) if invested and r["asset_type"] != "cash" else None
        if r["cost_basis"] and not r["basis_incomplete"]:
            r["gain"] = r["value"] - r["cost_basis"]
            r["gain_pct"] = r["gain"] / r["cost_basis"]
        else:
            r["gain"] = r["gain_pct"] = None

    with_basis = [r for r in rows if r["gain"] is not None]
    basis_total = sum(r["cost_basis"] for r in with_basis)
    gain_total = sum(r["gain"] for r in with_basis)
    top = max((r for r in rows if r["asset_type"] != "cash"),
              key=lambda r: r["value"], default=None)

    type_order = ["equity", "etf", "mutual_fund", "other", None, "cash"]
    groups = []
    for t in type_order:
        members = [r for r in rows if r["asset_type"] == t]
        if members:
            groups.append({"type": t or "unclassified", "rows": members,
                           "value": sum(r["value"] for r in members)})

    # 30,000 ft: full net worth by class (manual accounts included), by account
    dates, class_series = nw_model.get_class_series()
    alloc_class = {c: (class_series[c][-1] if class_series[c] else 0.0)
                   for c in nw_model.CLASS_ORDER}
    nw_total = sum(alloc_class.values())
    balances = nw_model.get_latest_balances()
    accounts = account_model.get_all()
    alloc_accounts = sorted(
        [{"name": a["name"], "value": balances[a["id"]],
          "cls": a["asset_class"] or "other"}
         for a in accounts if balances.get(a["id"])],
        key=lambda x: -x["value"])

    meta_direct, meta_indirect = critic.look_through_meta(rows)
    meta = next((r for r in rows if r["symbol"] == "META"), None)
    vest_account = next(
        (a for a in accounts if "meta" in (a["name"] or "").lower()),
        next((a for a in accounts if a["type"] == "brokerage"), None))

    return render_template(
        "net_worth/equities.html",
        holdings_date=holdings_date, groups=groups,
        total=total, cash=cash, invested=invested,
        basis_total=basis_total, gain_total=gain_total,
        gain_pct=(gain_total / basis_total) if basis_total else None,
        top=top, vest_ytd=vest_ytd, vest_year=year, meta=meta,
        vests=vests, accounts=accounts,
        vest_account_id=vest_account["id"] if vest_account else None,
        today=date.today().isoformat(),
        asset_types=["equity", "etf", "mutual_fund", "cash", "other"],
        # Phase 9 additions
        alloc_class=alloc_class, nw_total=nw_total, alloc_accounts=alloc_accounts,
        class_order=nw_model.CLASS_ORDER,
        critic_checks=critic.checks(rows),
        income=inv_model.income_ytd(year),
        meta_direct=meta_direct, meta_indirect=meta_indirect,
    )


@bp.route("/activity")
def activity():
    year = int(request.args.get("year", date.today().year))
    account_id = request.args.get("account_id") or None
    type_ = request.args.get("type") or None

    rows = inv_model.get_all(account_id=account_id, year=year, type_=type_)

    # Reconciliation: ledger deposits vs the cashflow "Investments" row.
    # A mismatch usually means a brokerage transfer was miscategorized on the
    # cash side (or simply not yet imported).
    deposits = inv_model.monthly_deposits(year)
    invest_flow = {r["month"]: r["amount"] for r in agg.monthly_cashflow(year)
                   if r["kind"] == "investment"}
    recon = []
    for month in sorted(set(deposits) | set(invest_flow)):
        d, f = deposits.get(month, 0.0), invest_flow.get(month, 0.0)
        recon.append({"month": month, "ledger": d, "cashflow": f,
                      "ok": abs(d - f) < 1.0})

    return render_template(
        "investments/activity.html",
        rows=rows, year=year, recon=recon,
        income=inv_model.income_ytd(year),
        accounts=account_model.get_all(),
        filters={"account_id": account_id, "type": type_},
        years=list(range(date.today().year, date.today().year - 6, -1)),
    )
