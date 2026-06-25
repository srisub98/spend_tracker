"""Seed a throwaway database with demo accounts for tests and local demos.

Two consumers:
  * the pytest suite imports SEED_ACCOUNTS / seed_accounts() (see tests/python/conftest.py)
  * the Playwright e2e webServer runs this directly to populate the test DB before
    the Flask app boots (see playwright.config.ts)

Honors DB_PATH from the environment, so always point it at a scratch file — never
your real database:

    DB_PATH=data/e2e_test.db python scripts/seed_test_db.py
"""
import os
import sys

# Allow running as a script (python scripts/seed_test_db.py) — put the repo root,
# not scripts/, at the front of sys.path so `import app` / `import config` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Demo accounts whose `institution` matches the providers in tests/fixtures/.
# Amex's CSV reports charges as positive, so it imports with sign-flip on; Schwab
# carries an external_ref matching schwab-positions.csv's account number.
SEED_ACCOUNTS = [
    {"name": "Citi Checking",       "type_": "checking",  "institution": "Citi"},
    {"name": "Citi Double Cash",    "type_": "credit",    "institution": "Citi"},
    {"name": "Amex Gold",           "type_": "credit",    "institution": "Amex",
     "flip_amount_signs": 1},
    {"name": "Capital One Savings", "type_": "savings",   "institution": "Capital One"},
    {"name": "Schwab Brokerage",    "type_": "brokerage", "institution": "Schwab",
     "asset_class": "stocks", "external_ref": "842"},
]


def seed_accounts():
    """Init the DB (schema + category/rule seeds) and add any missing demo
    accounts. Idempotent — safe to run repeatedly. Returns the count created."""
    from app import app
    from database.db import init_db
    import models.account as account_model

    init_db(app)
    created = 0
    with app.app_context():
        existing = {a["name"] for a in account_model.get_all()}
        for acct in SEED_ACCOUNTS:
            if acct["name"] not in existing:
                account_model.create(**acct)
                created += 1
    return created


if __name__ == "__main__":
    n = seed_accounts()
    print(f"Seeded {n} demo account(s) into {os.environ.get('DB_PATH', 'data/finance.db')}.")
