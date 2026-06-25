"""Schwab holdings export parsing — pure file parse, no DB."""
from pytest import approx

from services.holdings_parser import parse_holdings


def test_schwab_positions(fixtures_dir):
    sections = parse_holdings(str(fixtures_dir / "schwab-positions.csv"))
    assert len(sections) == 1
    s = sections[0]
    assert s["institution"] == "Schwab"
    assert s["account_ref"] == "842"
    assert s["total"] == approx(176786.47)

    syms = {p["symbol"] for p in s["positions"]}
    assert {"VTI", "AAPL"} <= syms
    cash = [p for p in s["positions"] if p["symbol"] is None]
    assert len(cash) == 1 and cash[0]["asset_type"] == "cash"
    # positions sum to the file's own account-total row
    assert sum(p["market_value"] for p in s["positions"]) == approx(s["total"])
