"""
Brokerage holdings CSV parsers (PRD Phase 4a). Local files only.

Supported formats (built from documented exports; the import preview will reveal
any drift in real files — adjust here if a section parses empty):

Schwab "Positions" export (single- or all-accounts):
    "Positions for account Individual ...842 as of 09:32 PM ET, 2026/06/09"
    <blank>
    "Symbol","Description","Qty (Quantity)","Price",...,"Mkt Val (Market Value)",...,"Security Type"
    "VTI","VANGUARD TOTAL STOCK MARKET ETF","500","$305.12",...
    "Cash & Cash Investments","--","--",...,"$4,386.47",...
    "Account Total","--",...,"$241,006.47",...
  All-accounts exports repeat the "Positions for account" line per section.

Vanguard download-center CSV (ofxdownload.csv) — holdings section then a
transactions section with a different header; we parse only the first:
    Account Number,Investment Name,Symbol,Shares,Share Price,Total Value
    12345678,Vanguard Total Stock Market...,VTSAX,800.123,132.45,105976.29

Output of parse_holdings(): list of sections:
    {institution, account_ref, positions: [{symbol, description, quantity,
     price, market_value}], total}      # total = file's own account-total row, if any
"""

import csv
import re


def _num(s):
    if s is None:
        return None
    s = str(s).strip().replace("$", "").replace(",", "").replace("%", "")
    if not s or s in ("--", "N/A", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_asset_type(raw):
    """Normalize the file's Asset/Security Type to: equity|etf|mutual_fund|cash|other."""
    t = (raw or "").lower()
    if not t or t == "--":
        return None
    if "cash" in t or "money market" in t:
        return "cash"
    if "etf" in t or "closed end" in t:
        return "etf"
    if "mutual fund" in t:
        return "mutual_fund"
    if "equity" in t:
        return "equity"
    return "other"


def detect_format(filepath):
    with open(filepath, newline="", encoding="utf-8-sig", errors="replace") as f:
        head = f.read(2048)
    if "Positions for account" in head:
        return "schwab"
    if re.search(r"^\s*\"?Account Number\"?\s*,\s*\"?Investment Name", head, re.MULTILINE):
        return "vanguard"
    return None


def parse_holdings(filepath):
    fmt = detect_format(filepath)
    if fmt == "schwab":
        return parse_schwab(filepath)
    if fmt == "vanguard":
        return parse_vanguard(filepath)
    raise ValueError(
        "Unrecognized holdings format — expected a Schwab Positions export "
        "('Positions for account …' on line 1) or a Vanguard download-center CSV "
        "('Account Number,Investment Name,…' header)."
    )


def parse_schwab(filepath):
    sections = []
    current = None
    header_idx = None  # column name -> index for the current section

    with open(filepath, newline="", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.reader(f):
            if not row or all(not c.strip() for c in row):
                continue
            first = row[0].strip()

            if first.startswith("Positions for account"):
                # e.g. "Positions for account Individual ...842 as of ..."
                ref_match = re.search(r"\.\.\.\s*(\w+)", first)
                current = {"institution": "Schwab",
                           "account_ref": ref_match.group(1) if ref_match else first,
                           "positions": [], "total": None}
                sections.append(current)
                header_idx = None
                continue
            if current is None:
                continue

            if header_idx is None:
                if first == "Symbol":
                    header_idx = {}
                    for i, col in enumerate(row):
                        col = col.strip()
                        if col == "Symbol":
                            header_idx["symbol"] = i
                        elif col == "Description":
                            header_idx["description"] = i
                        elif col.startswith("Qty"):
                            header_idx["quantity"] = i
                        elif col == "Price":
                            header_idx["price"] = i
                        elif col.startswith("Mkt Val"):
                            header_idx["value"] = i
                        elif col.startswith("Cost Basis"):
                            header_idx["cost"] = i
                        elif col in ("Security Type", "Asset Type"):
                            header_idx["type"] = i
                continue

            def cell(key):
                i = header_idx.get(key)
                return row[i].strip() if i is not None and i < len(row) else None

            symbol = first
            # Schwab labels the total row "Positions Total" (older exports: "Account Total")
            if symbol in ("Account Total", "Positions Total"):
                current["total"] = _num(cell("value"))
                header_idx = None  # section done
                continue
            value = _num(cell("value"))
            if value is None:
                continue
            asset_type = _norm_asset_type(cell("type"))
            is_sweep = symbol.lower().startswith("cash")
            if is_sweep:
                asset_type = "cash"
            current["positions"].append({
                "symbol": None if is_sweep else symbol,
                "description": "Cash & Cash Investments" if is_sweep else (cell("description") or ""),
                "quantity": _num(cell("quantity")),
                "price": _num(cell("price")),
                "market_value": value,
                "asset_type": asset_type,
                "cost_basis": _num(cell("cost")),
            })
    return [s for s in sections if s["positions"]]


def parse_vanguard(filepath):
    sections = {}
    in_holdings = False
    with open(filepath, newline="", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.reader(f):
            if not row or all(not c.strip() for c in row):
                continue
            first = row[0].strip()
            if first == "Account Number":
                # holdings header has "Investment Name" second; the later
                # transactions header has "Trade Date" — stop there.
                in_holdings = len(row) > 1 and row[1].strip() == "Investment Name"
                continue
            if not in_holdings:
                continue
            if len(row) < 6:
                continue
            ref = first
            value = _num(row[5])
            if value is None:
                continue
            section = sections.setdefault(ref, {
                "institution": "Vanguard", "account_ref": ref,
                "positions": [], "total": None})
            name = row[1].strip()
            symbol = row[2].strip() or None
            is_cash = "settlement" in name.lower() or "money market" in name.lower()
            section["positions"].append({
                "symbol": None if is_cash else symbol,
                "description": name,
                "quantity": _num(row[3]),
                "price": _num(row[4]),
                "market_value": value,
                "asset_type": "cash" if is_cash else None,  # Vanguard file has no type column
                "cost_basis": None,
            })
    return list(sections.values())
