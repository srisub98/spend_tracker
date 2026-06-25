"""
Vanguard monthly statement PDF parser (PRD-2 Phase 8).

The statement has everything the download-center CSV lacks: per-holding cost
basis + unrealized G/L, completed trades, deposits, and YTD income. pypdf
extracts the text but runs table columns together, so every numeric split is
validated arithmetically before it's accepted:
  - holding rows:  basis + unrealized == market value, qty × price ≈ market value
  - trade rows:    qty × price ≈ |amount|
  - whole file:    Σ holdings ≈ statement total value
Raw matched text is kept on every row for audit (like transactions.raw_csv_row).
"""

import re
from datetime import datetime
from pypdf import PdfReader


class VanguardParseError(ValueError):
    pass


# Strict thousand-grouping keeps the run-together numbers nearly unambiguous.
_M2 = r"\d{1,3}(?:,\d{3})*\.\d{2}"     # money, 2 decimals
_Q4 = r"\d{1,3}(?:,\d{3})*\.\d{4}"     # quantity, 4 decimals

# No \b before the symbol: pypdf runs the column header's "...2026" straight
# into the ticker ("2026VDIGX"), and digit→letter is not a word boundary.
_HOLDING_BLOB = re.compile(
    r"(?<![A-Z])([A-Z]{2,5})\s+(-?\$?[\d,]+\.\d{2}[\d,.$\s-]*)")

_TRADE = re.compile(
    r"(\d{2}/\d{2})(\d{2}/\d{2})([A-Z]{2,5})VANGUARD(Buy|Sell)(?:Cash|Margin)?"
    r"([\d,]+\.\d{4})\$?([\d,]+\.\d{2}?)((?:[\d,]+\.\d{2}))(-?\$?[\d,]+\.\d{2})")

_CASHFLOW = re.compile(
    r"(\d{2}/\d{2})(\d{2}/\d{2})-\s*(.*?)(Funds Received|Funds Paid)"
    r"[-\s]*\$?-?([\d,]+\.\d{2})")


def _num(s):
    return float(s.replace(",", "").replace("$", ""))


def _split_holding(blob):
    """Split a run-together 6-number holdings blob into
    (unrealized, basis, qty, price, prior, current); validation-driven."""
    clean = re.sub(r"[$\s]", "", blob)
    for price_dp in (2, 3, 4):
        m = re.match(
            rf"(-?{_M2})({_M2})({_Q4})(\d{{1,3}}(?:,\d{{3}})*\.\d{{{price_dp}}})"
            rf"({_M2})({_M2})$", clean)
        if not m:
            continue
        unreal, basis, qty, price, prior, cur = (_num(g) for g in m.groups())
        if abs((basis + unreal) - cur) > 0.02:
            continue
        if qty and abs(qty * price - cur) > max(1.0, cur * 0.002):
            continue
        return unreal, basis, qty, price, prior, cur
    return None


def _statement_date(text):
    m = re.search(r"([A-Z][a-z]+) (\d{1,2}), (\d{4}), monthly", text)
    if not m:
        raise VanguardParseError("Not a Vanguard monthly statement (no statement date).")
    return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()


def _with_year(mmdd, stmt_date):
    mm, dd = int(mmdd[:2]), int(mmdd[3:5])
    year = stmt_date.year - 1 if mm > stmt_date.month else stmt_date.year
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def parse_statement(path):
    reader = PdfReader(path)
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    if "Vanguard" not in text:
        raise VanguardParseError("Doesn't look like a Vanguard statement.")

    stmt_date = _statement_date(text)
    ref = re.search(r"XXXX(\d{4})", text)
    total = re.search(r"Statement overview\s*\$(" + _M2 + ")", text)
    total_value = _num(total.group(1)) if total else None

    # ---- Holdings (between the holdings header and the activity section) ----
    hold_start = text.find("Balances and holdings")
    hold_end = text.find("Account activity")
    hold_text = text[hold_start:hold_end if hold_end > hold_start else len(text)]
    mf_pos = hold_text.find("Mutual funds")
    etf_pos = hold_text.find("ETFs")

    holdings, seen = [], set()
    for m in _HOLDING_BLOB.finditer(hold_text):
        symbol = m.group(1)
        if symbol in seen:
            continue
        parts = _split_holding(m.group(2))
        if not parts:
            continue
        unreal, basis, qty, price, prior, cur = parts
        # description follows the blob, up to the est-income footnote
        tail = hold_text[m.end():m.end() + 80]
        desc = re.split(r"Est\. annual|Total ", tail)[0]
        desc = re.sub(r"^VANGUARD", "VANGUARD ", desc.replace("\n", " ")).strip()
        if etf_pos > -1 and m.start() > etf_pos:
            asset_type = "etf"
        elif mf_pos > -1 and m.start() > mf_pos:
            asset_type = "mutual_fund"
        else:
            asset_type = "other"
        seen.add(symbol)
        holdings.append({
            "symbol": symbol, "description": desc or symbol,
            "quantity": qty, "price": price, "market_value": cur,
            "cost_basis": basis, "unrealized": unreal,
            "asset_type": asset_type, "raw": m.group(0)[:200],
        })

    # Sweep / money-market balance (cash) if nonzero
    sweep = re.search(r"Total Sweep Balance\$(" + _M2 + r")\$(" + _M2 + ")", text)
    if sweep and _num(sweep.group(2)) > 0:
        holdings.append({
            "symbol": None, "description": "Settlement fund (sweep)",
            "quantity": None, "price": None, "market_value": _num(sweep.group(2)),
            "cost_basis": None, "unrealized": None,
            "asset_type": "cash", "raw": sweep.group(0),
        })

    # ---- Activity: trades + cash movements ----
    activity = []
    for m in _TRADE.finditer(text):
        settle, trade, symbol, ttype, qty, p1, p2, amt = m.groups()
        qty, amount = _num(qty), _num(amt)
        # price+fees run together: enumerate the split, validate qty×price≈|amount|
        price = fees = None
        for cand_price, cand_fees in ((p1, p2), (p1 + p2, "0")):
            try:
                cp = _num(cand_price)
            except ValueError:
                continue
            if abs(qty * cp - abs(amount)) <= max(0.5, abs(amount) * 0.005):
                price, fees = cp, _num(cand_fees) if cand_fees != "0" else 0.0
                break
        if price is None:
            price = abs(amount) / qty if qty else None
            fees = 0.0
        if ttype == "Buy" and amount > 0:
            amount = -amount
        activity.append({
            "date": _with_year(trade, stmt_date), "settle_date": _with_year(settle, stmt_date),
            "symbol": symbol, "type": ttype.lower(), "quantity": qty,
            "price": price, "fees": fees, "amount": amount, "raw": m.group(0)[:200],
        })
    for m in _CASHFLOW.finditer(text):
        settle, trade, desc, direction, amt = m.groups()
        amount = _num(amt)
        ttype = "deposit" if direction == "Funds Received" else "withdrawal"
        if ttype == "withdrawal":
            amount = -amount
        activity.append({
            "date": _with_year(trade, stmt_date), "settle_date": _with_year(settle, stmt_date),
            "symbol": None, "type": ttype, "quantity": None, "price": None,
            "fees": 0.0, "amount": amount,
            "raw": (desc.strip() + " " + m.group(0)[-40:])[:200],
        })

    # ---- YTD income summary ----
    income = {}
    ym = re.search(r"Year-to-date((?:[\d,]+\.\d{2}){6})", text.replace(" ", ""))
    if ym:
        vals = [_num(v) for v in re.findall(_M2, ym.group(1))]
        if len(vals) == 6:
            income = dict(zip(
                ["dividends", "interest", "tax_exempt", "capgain_st", "capgain_lt", "other"],
                vals))

    # ---- Validation ----
    problems = []
    held = sum(h["market_value"] for h in holdings)
    if total_value is not None and abs(held - total_value) > 0.05:
        problems.append(f"Holdings sum ${held:,.2f} ≠ statement total ${total_value:,.2f}")
    if not holdings:
        problems.append("No holdings parsed — statement format may have drifted.")

    return {
        "statement_date": stmt_date.isoformat(),
        "account_ref": ref.group(1) if ref else None,
        "total_value": total_value if total_value is not None else held,
        "holdings": holdings,
        "activity": sorted(activity, key=lambda a: a["date"]),
        "income_ytd": income,
        "problems": problems,
    }
