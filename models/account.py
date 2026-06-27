import json
from database.db import get_db

def get_all():
    return get_db().execute(
        "SELECT * FROM accounts ORDER BY name"
    ).fetchall()

def get_by_id(account_id):
    return get_db().execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()

def create(name, type_, institution, currency="USD", is_liability=0,
           asset_class=None, external_ref=None, flip_amount_signs=0,
           plaid_account_id=None, plaid_item_id=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO accounts (name, type, institution, currency, is_liability,
                                 asset_class, external_ref, flip_amount_signs,
                                 plaid_account_id, plaid_item_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (name, type_, institution, currency, is_liability,
         asset_class, external_ref, flip_amount_signs,
         plaid_account_id, plaid_item_id),
    )
    db.commit()
    return cur.lastrowid


def get_by_plaid_account_id(plaid_account_id):
    return get_db().execute(
        "SELECT * FROM accounts WHERE plaid_account_id=?", (plaid_account_id,)
    ).fetchone()


def link_plaid(account_id, plaid_account_id, plaid_item_id):
    """Attach an existing local account to a Plaid account (e.g. matched by last-4)."""
    db = get_db()
    db.execute(
        "UPDATE accounts SET plaid_account_id=?, plaid_item_id=? WHERE id=?",
        (plaid_account_id, plaid_item_id, account_id),
    )
    db.commit()

def update(account_id, name, type_, institution,
           asset_class=None, external_ref=None, flip_amount_signs=0):
    db = get_db()
    db.execute(
        """UPDATE accounts SET name=?, type=?, institution=?,
                               asset_class=?, external_ref=?, flip_amount_signs=?
           WHERE id=?""",
        (name, type_, institution, asset_class, external_ref, flip_amount_signs, account_id),
    )
    db.commit()

def set_external_ref(account_id, external_ref):
    db = get_db()
    db.execute("UPDATE accounts SET external_ref=? WHERE id=?", (external_ref, account_id))
    db.commit()

def update_csv_settings(account_id, mapping, flip_amount_signs):
    """Persist the confirmed import-preview settings so future uploads for this
    bank parse correctly without re-mapping."""
    db = get_db()
    db.execute(
        "UPDATE accounts SET csv_mapping=?, flip_amount_signs=? WHERE id=?",
        (json.dumps(mapping) if mapping else None, 1 if flip_amount_signs else 0, account_id),
    )
    db.commit()

def delete(account_id):
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id=?", (account_id,)
    ).fetchone()[0]
    if count > 0:
        raise ValueError("Cannot delete account with existing transactions.")
    db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    db.commit()


def purge_plaid_links():
    """Admin reset (sandbox): undo Plaid account linkage. An account created by a Plaid
    link (transaction-less once delete_plaid_synced has run) is deleted; a pre-existing
    account that was only matched by last-4 keeps its data and is just unlinked. Returns
    {"deleted": [names], "unlinked": [names]}."""
    db = get_db()
    deleted, unlinked = [], []
    for a in db.execute(
            "SELECT id, name FROM accounts WHERE plaid_account_id IS NOT NULL").fetchall():
        has_tx = db.execute(
            "SELECT 1 FROM transactions WHERE account_id=? LIMIT 1", (a["id"],)).fetchone()
        if has_tx:
            db.execute(
                "UPDATE accounts SET plaid_account_id=NULL, plaid_item_id=NULL WHERE id=?",
                (a["id"],))
            unlinked.append(a["name"])
        else:
            db.execute("DELETE FROM snapshot_account_balances WHERE account_id=?", (a["id"],))
            db.execute("DELETE FROM holdings WHERE account_id=?", (a["id"],))
            db.execute("DELETE FROM accounts WHERE id=?", (a["id"],))
            deleted.append(a["name"])
    db.commit()
    return {"deleted": deleted, "unlinked": unlinked}
