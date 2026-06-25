import sqlite3
import os
from flask import g
import config

def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(config.DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db(app):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    # Ensure the DB's folder exists — on a fresh clone data/ is git-ignored and
    # absent, so this is what makes the very first run (and CI) work.
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    with app.app_context():
        db = sqlite3.connect(config.DB_PATH)
        with open(schema_path) as f:
            db.executescript(f.read())
        _migrate(db)
        _seed(db)
        db.commit()
        db.close()
    # Register the teardown once — Flask forbids it after the first request, and
    # tests legitimately call init_db() repeatedly (fresh temp DB each time).
    if not getattr(app, "_close_db_registered", False):
        app.teardown_appcontext(close_db)
        app._close_db_registered = True


def _migrate(db):
    """Additive migrations for DBs created before a column existed (schema.sql's
    CREATE IF NOT EXISTS won't alter existing tables)."""
    def ensure_column(table, column, ddl):
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
        if column not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    ensure_column("accounts", "csv_mapping", "csv_mapping TEXT")
    ensure_column("holdings", "asset_type", "asset_type TEXT")
    ensure_column("holdings", "cost_basis", "cost_basis REAL")
    # PRD-2 Phase 7: true spend + per-person settlement
    ensure_column("transactions", "my_share", "my_share REAL")
    ensure_column("outing_line_items", "transaction_id",
                  "transaction_id INTEGER REFERENCES transactions(id)")
    ensure_column("outing_participants", "person_id",
                  "person_id INTEGER REFERENCES people(id)")
    # Plaid sync (optional): account linkage + per-transaction id for idempotent re-sync
    ensure_column("accounts", "plaid_account_id", "plaid_account_id TEXT")
    ensure_column("accounts", "plaid_item_id", "plaid_item_id TEXT")
    ensure_column("transactions", "plaid_transaction_id", "plaid_transaction_id TEXT")


def _seed(db):
    """Populate categories and rules on first init (only when the tables are empty)."""
    from database.seed_data import CATEGORY_SEED
    from services.rules import seed_rows

    if db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO categories (name, kind, sort_order) VALUES (?,?,?)",
            CATEGORY_SEED,
        )
    if db.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO rules (pattern, match_type, category, priority) VALUES (?,?,?,?)",
            seed_rows(),
        )
