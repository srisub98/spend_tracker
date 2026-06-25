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
           asset_class=None, external_ref=None, flip_amount_signs=0):
    db = get_db()
    cur = db.execute(
        """INSERT INTO accounts (name, type, institution, currency, is_liability,
                                 asset_class, external_ref, flip_amount_signs)
           VALUES (?,?,?,?,?,?,?,?)""",
        (name, type_, institution, currency, is_liability,
         asset_class, external_ref, flip_amount_signs),
    )
    db.commit()
    return cur.lastrowid

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
