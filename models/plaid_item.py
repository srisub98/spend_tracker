"""Plaid Item storage (one row per linked institution login).

Mirrors the single-purpose token storage of models around schwab_tokens, but Plaid
supports many Items, so this is a normal multi-row table keyed by Plaid's item_id.
The access_token is a long-lived bearer secret — the whole DB is gitignored.
"""
from datetime import datetime
from database.db import get_db


def get_all():
    return get_db().execute(
        "SELECT * FROM plaid_items WHERE status='active' ORDER BY institution, id"
    ).fetchall()


def get_by_item_id(item_id):
    return get_db().execute(
        "SELECT * FROM plaid_items WHERE item_id=?", (item_id,)
    ).fetchone()


def upsert(item_id, access_token, institution=None):
    """Store a freshly linked Item (or refresh its token on re-link). Leaves the
    sync cursor untouched on conflict so an existing Item keeps syncing incrementally."""
    db = get_db()
    now = datetime.now().isoformat()
    db.execute(
        """INSERT INTO plaid_items (item_id, access_token, institution, status, updated_at)
           VALUES (?,?,?,'active',?)
           ON CONFLICT(item_id) DO UPDATE SET access_token=excluded.access_token,
               institution=COALESCE(excluded.institution, plaid_items.institution),
               status='active', updated_at=excluded.updated_at""",
        (item_id, access_token, institution, now),
    )
    db.commit()


def set_cursor(item_id, cursor):
    db = get_db()
    db.execute(
        "UPDATE plaid_items SET cursor=?, updated_at=? WHERE item_id=?",
        (cursor, datetime.now().isoformat(), item_id),
    )
    db.commit()


def delete(item_id):
    """Soft-unlink: mark inactive so it drops out of the UI and sync loop. Synced
    transactions stay (they're real history); the access_token is cleared."""
    db = get_db()
    db.execute(
        "UPDATE plaid_items SET status='removed', access_token='', updated_at=? WHERE item_id=?",
        (datetime.now().isoformat(), item_id),
    )
    db.commit()


def delete_all():
    """Admin reset (sandbox): hard-delete every linked Item (vs the soft status flip of
    delete()), so re-linking starts clean. Returns the number of rows removed."""
    db = get_db()
    n = db.execute("DELETE FROM plaid_items").rowcount
    db.commit()
    return n
