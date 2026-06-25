"""Parser coverage across the bank-CSV shapes in tests/fixtures/.

parse_csv loads the rule registry from the DB, so these run inside an app
context backed by the seeded temp DB (the `flask_app` fixture)."""
from pytest import approx


def _by_desc(rows):
    return {r["description"]: r for r in rows}


def test_citi_checking_debit_credit_columns(flask_app, fixtures_dir):
    from services.csv_parser import parse_csv
    with flask_app.app_context():
        rows, stats = parse_csv(str(fixtures_dir / "citi-checking.csv"), account_id=1)
    by = _by_desc(rows)
    assert stats["total"] == 4
    # debit -> outflow (negative), credit -> inflow (positive)
    assert by["WHOLE FOODS MARKET #123"]["amount"] == approx(-52.13)
    assert by["WHOLE FOODS MARKET #123"]["category"] == "Groceries"
    assert by["PAYROLL DIRECT DEP ACME CORP"]["amount"] == approx(3200.00)
    assert by["PAYROLL DIRECT DEP ACME CORP"]["category"] == "Paycheck"
    assert by["UBER EATS"]["amount"] == approx(-28.40)
    assert by["UBER EATS"]["category"] == "Food"          # beats the "uber" -> Car rule
    assert by["TRANSFER TO SAVINGS"]["category"] == "Transfers"


def test_amex_single_amount_with_sign_flip(flask_app, fixtures_dir):
    from services.csv_parser import parse_csv
    with flask_app.app_context():
        rows, _ = parse_csv(str(fixtures_dir / "amex.csv"), account_id=3, flip_signs=True)
    by = _by_desc(rows)
    assert by["DELTA AIR LINES"]["amount"] == approx(-342.50)   # charge -> negative after flip
    assert by["DELTA AIR LINES"]["category"] == "Travel"
    assert by["UBER TRIP 0612"]["amount"] == approx(-18.90)
    assert by["UBER TRIP 0612"]["category"] == "Car"
    assert by["MOBILE PAYMENT - THANK YOU"]["amount"] == approx(500.00)  # payment -> positive
    assert by["MOBILE PAYMENT - THANK YOU"]["category"] == "Transfers"


def test_capitalone_amount_plus_type_column(flask_app, fixtures_dir):
    from services.csv_parser import parse_csv
    with flask_app.app_context():
        rows, _ = parse_csv(str(fixtures_dir / "capitalone.csv"), account_id=4)
    by = _by_desc(rows)
    assert by["INTEREST PAID"]["amount"] == approx(4.12)          # Credit type -> positive
    assert by["INTEREST PAID"]["category"] == "Interest"
    assert by["ACH WITHDRAWAL TRANSFER"]["amount"] == approx(-200.00)  # Debit type -> negative
    assert by["ACH WITHDRAWAL TRANSFER"]["category"] == "Transfers"


def test_dates_normalized_to_iso(flask_app, fixtures_dir):
    from services.csv_parser import parse_csv
    with flask_app.app_context():
        rows, _ = parse_csv(str(fixtures_dir / "amex.csv"), account_id=3)  # MM/DD/YYYY in file
    assert rows[0]["date"] == "2026-06-02"


def test_unmatched_rows_have_no_category(flask_app, fixtures_dir):
    from services.csv_parser import parse_csv
    with flask_app.app_context():
        rows, stats = parse_csv(str(fixtures_dir / "unmatched.csv"), account_id=2)
    assert stats["rule_matched"] == 0
    assert all(r["category"] is None for r in rows)
