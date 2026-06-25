"""Rule-ordering tests — pure, no DB.

seed_rows() emits rows in (priority, insertion) order, which is exactly the
(priority, id) order load_rules() reads back from the DB, so compiling them
directly mirrors production matching."""
from services.rules import SEED_RULES, seed_rows, apply_rules


def _compiled():
    return [("substring", pat.lower(), cat) for (pat, _mt, cat, _pri) in seed_rows()]


def test_uber_eats_beats_uber():
    rules = _compiled()
    assert apply_rules("UBER EATS", rules) == "Food"
    assert apply_rules("UBER TRIP 0612", rules) == "Car"


def test_amazon_prime_beats_amazon():
    rules = _compiled()
    assert apply_rules("AMAZON PRIME VIDEO", rules) == "Entertainment"
    assert apply_rules("AMAZON MARKETPLACE", rules) == "Misc"


def test_no_match_returns_none():
    assert apply_rules("QZX MERCHANT 4471", _compiled()) is None


def test_seed_rows_shape_and_categories():
    from database.seed_data import CATEGORY_SEED
    rows = seed_rows()
    assert rows, "seed rules should not be empty"
    assert all(len(r) == 4 and r[1] == "substring" for r in rows)
    valid = {name for (name, _kind, _sort) in CATEGORY_SEED}
    assert {r[2] for r in rows} <= valid, "every rule maps to a seeded category"
