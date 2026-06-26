"""
Investment critic v1 (PRD-2 Phase 9): rule-based checks over the latest
holdings. Fund metadata is a small hand-maintained map of look-through
weight for a single employer's stock inside common index/growth funds —
sample weights below are calibrated for one mega-cap tech employer; if you
set EMPLOYER_STOCK_SYMBOL to a different company, edit each fund's
`employer_w` to that company's actual weight in the fund (refresh
quarterly, they drift slowly).
"""
import config

META_AS_OF = "2026-06"

# expense ratio (%/yr), approx employer-stock look-through weight (% of fund), short note
FUND_META = {
    "VFIAX": {"er": 0.04, "employer_w": 2.5,  "note": "S&P 500"},
    "SPY":   {"er": 0.09, "employer_w": 2.5,  "note": "S&P 500"},
    "QQQ":   {"er": 0.20, "employer_w": 5.0,  "note": "Nasdaq-100"},
    "MGK":   {"er": 0.07, "employer_w": 5.0,  "note": "mega-cap growth"},
    "VONG":  {"er": 0.08, "employer_w": 4.5,  "note": "Russell 1000 growth"},
    "VIG":   {"er": 0.05, "employer_w": 0.0,  "note": "dividend appreciation"},
    "VDIGX": {"er": 0.29, "employer_w": 0.0,  "note": "active dividend growth"},
    "ARTIX": {"er": 1.19, "employer_w": 0.0,  "note": "active international"},
    "RPMGX": {"er": 0.77, "employer_w": 0.0,  "note": "active mid-cap growth"},
    "VHT":   {"er": 0.10, "employer_w": 0.0,  "note": "healthcare sector"},
    "VDC":   {"er": 0.10, "employer_w": 0.0,  "note": "consumer staples sector"},
    "VPU":   {"er": 0.10, "employer_w": 0.0,  "note": "utilities sector"},
    "XLE":   {"er": 0.09, "employer_w": 0.0,  "note": "energy sector"},
    "SWVXX": {"er": 0.34, "employer_w": 0.0,  "note": "money market"},
}

SP500_FUNDS = {"VFIAX", "SPY"}
GROWTH_FUNDS = {"QQQ", "MGK", "VONG"}


def checks(rows):
    """rows: latest holdings aggregated by symbol — dicts with symbol, value,
    asset_type. Returns list of {level: 'warn'|'info', title, body}."""
    out = []
    total = sum(r["value"] for r in rows)
    cash = sum(r["value"] for r in rows if r["asset_type"] == "cash")
    invested = total - cash
    if not invested:
        return out
    val = {r["symbol"]: r["value"] for r in rows}

    # 1. Look-through employer-stock concentration — no-op unless
    # EMPLOYER_STOCK_SYMBOL is set (see config.py).
    symbol = config.EMPLOYER_STOCK_SYMBOL
    if symbol:
        direct = val.get(symbol, 0.0)
        indirect = sum(v * FUND_META[s]["employer_w"] / 100
                       for s, v in val.items() if s in FUND_META)
        if direct:
            out.append({
                "level": "warn",
                "title": f"{symbol} is {(direct + indirect) / invested:.0%} of invested "
                         f"(look-through), and it's your employer",
                "body": f"${direct:,.0f} direct + ~${indirect:,.0f} inside your index/growth "
                        f"funds (S&P 500 ~2.5%, QQQ/MGK ~5% each, as of {META_AS_OF}). "
                        "Add the paycheck and unvested RSUs that also depend on it and "
                        "this is triple concentration — selling vested shares as they land "
                        "is the standard fix.",
            })

    # 2. Duplicate / overlapping funds
    sp = [s for s in SP500_FUNDS if val.get(s)]
    if len(sp) > 1:
        out.append({
            "level": "info",
            "title": "Two S&P 500 funds: " + " + ".join(sp),
            "body": "VFIAX and SPY track the same index — fine, but consolidating "
                    "simplifies rebalancing and tax-lot tracking.",
        })
    gr = [s for s in GROWTH_FUNDS if val.get(s)]
    if len(gr) > 1:
        gv = sum(val[s] for s in gr)
        out.append({
            "level": "info",
            "title": f"{len(gr)} overlapping growth funds ({' + '.join(gr)}) = ${gv:,.0f}",
            "body": "QQQ, MGK, and VONG share most of their top holdings (Apple, "
                    "Microsoft, Nvidia, Meta…). They move together — treat them as one "
                    "position when judging exposure.",
        })

    # 3. Cash drag
    if cash / total > 0.05:
        out.append({
            "level": "info",
            "title": f"Cash & money market is {cash / total:.0%} of holdings (${cash:,.0f})",
            "body": "Above a ~5% buffer this is drag vs your index funds long-term. "
                    "Fine if it's earmarked (taxes on vests, big purchase) — otherwise "
                    "consider putting a chunk to work.",
        })

    # 4. Expense audit
    fees = [(s, val[s] * FUND_META[s]["er"] / 100, FUND_META[s])
            for s in val if s in FUND_META and val[s]]
    annual = sum(f for _, f, _ in fees)
    expensive = [(s, f, m) for s, f, m in fees if m["er"] >= 0.5]
    if annual:
        body = f"≈${annual:,.0f}/yr across your funds (as of {META_AS_OF})."
        if expensive:
            body += " Costly: " + ", ".join(
                f"{s} ({m['er']:.2f}% = ${f:,.0f}/yr, {m['note']})"
                for s, f, m in expensive) + \
                " — each has a cheap index alternative if conviction fades."
        out.append({"level": "info", "title": "Fund fees", "body": body})

    return out


def look_through_employer(rows):
    """(direct $, indirect $) employer-stock exposure for the allocation
    header. Returns (0.0, 0.0) if EMPLOYER_STOCK_SYMBOL is unset."""
    symbol = config.EMPLOYER_STOCK_SYMBOL
    if not symbol:
        return 0.0, 0.0
    val = {r["symbol"]: r["value"] for r in rows}
    indirect = sum(v * FUND_META[s]["employer_w"] / 100
                   for s, v in val.items() if s in FUND_META)
    return val.get(symbol, 0.0), indirect
