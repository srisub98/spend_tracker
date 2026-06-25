from database.db import get_db

# --- People (PRD-2 Phase 7: settlement is per-person across outings) ---

def get_people():
    return get_db().execute("SELECT * FROM people ORDER BY name").fetchall()

def get_or_create_person(name):
    name = (name or "").strip()
    if not name:
        return None
    db = get_db()
    row = db.execute("SELECT id FROM people WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if row:
        return row["id"]
    cur = db.execute("INSERT INTO people (name) VALUES (?)", (name,))
    db.commit()
    return cur.lastrowid

def update_person(person_id, name=None, venmo_handle=None, notes=None):
    db = get_db()
    db.execute(
        "UPDATE people SET name=COALESCE(?, name), venmo_handle=COALESCE(?, venmo_handle), "
        "notes=COALESCE(?, notes) WHERE id=?",
        (name, venmo_handle, notes, person_id))
    db.commit()

def backfill_people():
    """One-time-ish: create people from existing participant names and link them."""
    db = get_db()
    for r in db.execute("SELECT DISTINCT name FROM outing_participants "
                        "WHERE person_id IS NULL AND name != ''").fetchall():
        pid = get_or_create_person(r["name"])
        db.execute("UPDATE outing_participants SET person_id=? "
                   "WHERE name=? AND person_id IS NULL", (pid, r["name"]))
    db.commit()


def person_ledger():
    """Per-person settlement view across ALL outings: unpaid total, outing detail,
    venmo handle. Joins on person_id when present, else by name."""
    db = get_db()
    rows = db.execute(
        """SELECT COALESCE(p.id, -1) AS person_id,
                  COALESCE(p.name, op.name) AS name,
                  p.venmo_handle,
                  op.id AS participant_id, op.is_paid, op.paid_at,
                  o.id AS outing_id, o.title, o.outing_date,
                  (SELECT COALESCE(SUM(oli.per_person_amount), 0)
                   FROM outing_line_items oli
                   WHERE oli.outing_id = o.id AND oli.paid_by_me = 1) AS share
           FROM outing_participants op
           JOIN outings o ON o.id = op.outing_id
           LEFT JOIN people p ON p.id = op.person_id
           ORDER BY name, o.outing_date DESC""").fetchall()
    people = {}
    for r in rows:
        entry = people.setdefault(r["name"], {
            "person_id": r["person_id"], "name": r["name"],
            "venmo_handle": r["venmo_handle"],
            "owed": 0.0, "settled": 0.0, "unpaid_items": [], "history": []})
        if r["is_paid"]:
            entry["settled"] += r["share"]
            entry["history"].append(dict(r))
        else:
            entry["owed"] += r["share"]
            entry["unpaid_items"].append(dict(r))
    return sorted(people.values(), key=lambda p: -p["owed"])


def settle_person(person_id):
    """Mark every unpaid participation of this person as paid."""
    db = get_db()
    cur = db.execute(
        "UPDATE outing_participants SET is_paid=1, paid_at=datetime('now') "
        "WHERE person_id=? AND is_paid=0", (person_id,))
    db.commit()
    return cur.rowcount


def total_receivable():
    """Total unsettled money owed to me across all outings."""
    row = get_db().execute(
        """SELECT COALESCE(SUM(share), 0) AS total FROM (
             SELECT (SELECT COALESCE(SUM(oli.per_person_amount), 0)
                     FROM outing_line_items oli
                     WHERE oli.outing_id = op.outing_id AND oli.paid_by_me = 1) AS share
             FROM outing_participants op WHERE op.is_paid = 0)""").fetchone()
    return row["total"]


# --- Split-a-transaction (PRD-2 Phase 7.2) ---

def split_transaction(tx, names_shares):
    """Create an outing + linked line item + participants from an imported card
    charge. names_shares: list of (name, share_amount). Sets transactions.my_share
    so the dashboard counts only my part. Returns outing_id."""
    db = get_db()
    total = abs(tx["amount"])
    others = round(sum(s for _, s in names_shares), 2)
    my_share_amt = round(total - others, 2)         # what's actually mine
    title = f"{(tx['description'] or 'Charge').strip()[:40]} — {tx['date']}"

    cur = db.execute(
        "INSERT INTO outings (title, outing_date, notes) VALUES (?,?,?)",
        (title, tx["date"], "from transaction split"))
    outing_id = cur.lastrowid
    db.execute(
        """INSERT INTO outing_line_items (outing_id, description, total_amount,
           paid_by_me, split_count, per_person_amount, transaction_id)
           VALUES (?,?,?,1,?,?,?)""",
        (outing_id, tx["description"], total, len(names_shares) + 1,
         names_shares[0][1] if names_shares else total, tx["id"]))
    for name, share in names_shares:
        pid = get_or_create_person(name)
        db.execute(
            "INSERT INTO outing_participants (outing_id, name, person_id) VALUES (?,?,?)",
            (outing_id, name, pid))
    # my_share keeps the transaction's sign (negative = expense)
    db.execute("UPDATE transactions SET my_share=? WHERE id=?",
               (-my_share_amt, tx["id"]))
    db.commit()
    return outing_id


def unsplit_transaction(transaction_id):
    """Remove the split link + my_share (deletes the auto-created outing if it
    only contained this one linked item)."""
    db = get_db()
    item = db.execute("SELECT * FROM outing_line_items WHERE transaction_id=?",
                      (transaction_id,)).fetchone()
    if item:
        siblings = db.execute(
            "SELECT COUNT(*) FROM outing_line_items WHERE outing_id=?",
            (item["outing_id"],)).fetchone()[0]
        db.execute("DELETE FROM outing_line_items WHERE id=?", (item["id"],))
        if siblings == 1:
            db.execute("DELETE FROM outing_participants WHERE outing_id=?", (item["outing_id"],))
            db.execute("DELETE FROM outings WHERE id=?", (item["outing_id"],))
    db.execute("UPDATE transactions SET my_share=NULL WHERE id=?", (transaction_id,))
    db.commit()

# --- Outings ---

def get_all_outings():
    return get_db().execute(
        "SELECT * FROM outings ORDER BY outing_date DESC"
    ).fetchall()

def get_outing(outing_id):
    return get_db().execute(
        "SELECT * FROM outings WHERE id=?", (outing_id,)
    ).fetchone()

def create_outing(title, outing_date, notes=""):
    db = get_db()
    cur = db.execute(
        "INSERT INTO outings (title, outing_date, notes) VALUES (?,?,?)",
        (title, outing_date, notes),
    )
    db.commit()
    return cur.lastrowid

def delete_outing(outing_id):
    db = get_db()
    db.execute("DELETE FROM outing_line_items WHERE outing_id=?", (outing_id,))
    db.execute("DELETE FROM outing_participants WHERE outing_id=?", (outing_id,))
    db.execute("DELETE FROM outings WHERE id=?", (outing_id,))
    db.commit()

# --- Participants ---

def get_participants(outing_id):
    return get_db().execute(
        "SELECT * FROM outing_participants WHERE outing_id=? ORDER BY name", (outing_id,)
    ).fetchall()

def add_participant(outing_id, name):
    db = get_db()
    cur = db.execute(
        "INSERT INTO outing_participants (outing_id, name) VALUES (?,?)",
        (outing_id, name),
    )
    db.commit()
    return cur.lastrowid

def mark_paid(participant_id):
    db = get_db()
    db.execute(
        "UPDATE outing_participants SET is_paid=1, paid_at=datetime('now') WHERE id=?",
        (participant_id,),
    )
    db.commit()

def mark_unpaid(participant_id):
    db = get_db()
    db.execute(
        "UPDATE outing_participants SET is_paid=0, paid_at=NULL WHERE id=?",
        (participant_id,),
    )
    db.commit()

# --- Line Items ---

def get_line_items(outing_id):
    return get_db().execute(
        "SELECT * FROM outing_line_items WHERE outing_id=? ORDER BY id", (outing_id,)
    ).fetchall()

def add_line_item(outing_id, description, total_amount, paid_by_me=1, split_count=2):
    per_person = round(total_amount / split_count, 2) if split_count > 0 else total_amount
    db = get_db()
    cur = db.execute(
        """INSERT INTO outing_line_items (outing_id, description, total_amount, paid_by_me, split_count, per_person_amount)
           VALUES (?,?,?,?,?,?)""",
        (outing_id, description, total_amount, paid_by_me, split_count, per_person),
    )
    db.commit()
    return cur.lastrowid

def delete_line_item(item_id):
    db = get_db()
    db.execute("DELETE FROM outing_line_items WHERE id=?", (item_id,))
    db.commit()

# --- Summary helpers ---

def get_outing_summary(outing_id):
    """Returns total owed per participant based on line items."""
    items = get_line_items(outing_id)
    participants = get_participants(outing_id)
    total_you_fronted = sum(i["total_amount"] for i in items if i["paid_by_me"])
    # Each participant owes their share of items you fronted
    per_person_shares = {}
    for item in items:
        if not item["paid_by_me"]:
            continue
        share = item["per_person_amount"] or round(item["total_amount"] / item["split_count"], 2)
        for p in participants:
            per_person_shares[p["id"]] = per_person_shares.get(p["id"], 0) + share
    return {
        "total_you_fronted": total_you_fronted,
        "per_person_shares": per_person_shares,
        "participants": participants,
        "items": items,
    }

def get_total_owed():
    """Total outstanding across all outings."""
    db = get_db()
    rows = db.execute(
        """SELECT op.name, SUM(oli.per_person_amount) as owed
           FROM outing_participants op
           JOIN outing_line_items oli ON oli.outing_id=op.outing_id
           WHERE op.is_paid=0 AND oli.paid_by_me=1
           GROUP BY op.name"""
    ).fetchall()
    return rows
