from database.db import get_db

def get_all(account_id=None, category=None, start_date=None, end_date=None, limit=500, offset=0, status=None):
    query = "SELECT t.*, a.name as account_name FROM transactions t JOIN accounts a ON t.account_id=a.id WHERE 1=1"
    params = []
    if account_id:
        query += " AND t.account_id=?"
        params.append(account_id)
    if category:
        query += " AND t.category=?"
        params.append(category)
    if start_date:
        query += " AND t.date>=?"
        params.append(start_date)
    if end_date:
        query += " AND t.date<=?"
        params.append(end_date)
    if status == "review":
        query += " AND (t.category_source IS NULL OR t.category_source='claude')"
    query += " ORDER BY t.date DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return get_db().execute(query, params).fetchall()

def count(account_id=None, category=None, start_date=None, end_date=None, status=None):
    query = "SELECT COUNT(*) FROM transactions t WHERE 1=1"
    params = []
    if account_id:
        query += " AND t.account_id=?"
        params.append(account_id)
    if category:
        query += " AND t.category=?"
        params.append(category)
    if start_date:
        query += " AND t.date>=?"
        params.append(start_date)
    if end_date:
        query += " AND t.date<=?"
        params.append(end_date)
    if status == "review":
        query += " AND (t.category_source IS NULL OR t.category_source='claude')"
    return get_db().execute(query, params).fetchone()[0]

def get_uncategorized_by_batch(batch_id):
    """Freshly imported rows that no rule matched (duplicates skipped by the
    insert don't carry this batch_id, so they're naturally excluded)."""
    return get_db().execute(
        "SELECT id, description, category FROM transactions "
        "WHERE import_batch_id=? AND category IS NULL ORDER BY id",
        (batch_id,),
    ).fetchall()

def get_uncategorized():
    return get_db().execute(
        "SELECT t.*, a.name as account_name FROM transactions t JOIN accounts a ON t.account_id=a.id "
        "WHERE t.category IS NULL OR t.category_source='claude' ORDER BY t.date DESC"
    ).fetchall()

def bulk_insert(rows):
    """rows: list of dicts with keys matching transactions columns. Uses INSERT OR IGNORE for dedup."""
    db = get_db()
    inserted = 0
    for row in rows:
        cur = db.execute(
            """INSERT OR IGNORE INTO transactions
               (account_id, date, description, amount, currency, category, category_source, raw_csv_row, import_batch_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                row["account_id"], row["date"], row["description"], row["amount"],
                row.get("currency", "USD"), row.get("category"), row.get("category_source"),
                row.get("raw_csv_row"), row.get("import_batch_id"),
            ),
        )
        inserted += cur.rowcount
    db.commit()
    return inserted

def insert_plaid_rows(rows, date_tolerance_days=3):
    """Insert Plaid-synced transactions without ever duplicating an existing row.

    rows: dicts shaped like csv_parser output, plus a required 'plaid_transaction_id'.
    Three-layer dedup (see plan Hard Requirement 2):
      1. Same plaid_transaction_id already stored → UPDATE in place (handles Plaid
         'modified' events like pending→posted) and keep any category already set.
      2. A non-Plaid row (e.g. a CSV import) for the same purchase already exists —
         matched on account + amount + a small date window, IGNORING description
         (Plaid's "Starbucks" never byte-matches a raw "STARBUCKS #1234" memo). Adopt
         the plaid_transaction_id onto that row so future syncs are idempotent, and
         don't insert a duplicate.
      3. Genuinely new → INSERT with the rule-assigned category.

    Returns {'inserted', 'updated', 'skipped'} (skipped = matched an existing CSV row).
    """
    db = get_db()
    inserted = updated = skipped = 0
    for row in rows:
        ptid = row["plaid_transaction_id"]
        amount = round(row["amount"], 2)

        existing = db.execute(
            "SELECT id FROM transactions WHERE plaid_transaction_id=?", (ptid,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE transactions SET date=?, description=?, amount=? WHERE id=?",
                (row["date"], row["description"], amount, existing["id"]),
            )
            updated += 1
            continue

        # Cross-source dedup. 0.005 tolerance absorbs float representation; the date
        # window absorbs posting lag. Identical-amount transactions a couple days
        # apart can in theory collapse into one — accepted tradeoff for "never
        # re-import what a CSV already brought in".
        dupe = db.execute(
            """SELECT id FROM transactions
               WHERE account_id=? AND plaid_transaction_id IS NULL
                 AND ABS(amount - ?) < 0.005
                 AND ABS(julianday(date) - julianday(?)) <= ?
               LIMIT 1""",
            (row["account_id"], amount, row["date"], date_tolerance_days),
        ).fetchone()
        if dupe:
            db.execute("UPDATE transactions SET plaid_transaction_id=? WHERE id=?",
                       (ptid, dupe["id"]))
            skipped += 1
            continue

        cur = db.execute(
            """INSERT OR IGNORE INTO transactions
               (account_id, date, description, amount, currency, category,
                category_source, import_batch_id, plaid_transaction_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (row["account_id"], row["date"], row["description"], amount,
             row.get("currency", "USD"), row.get("category"), row.get("category_source"),
             row.get("import_batch_id"), ptid),
        )
        inserted += cur.rowcount
    db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def remove_plaid_rows(plaid_transaction_ids):
    """Apply Plaid 'removed' events. Pure Plaid-origin rows (no raw_csv_row) are
    deleted; a CSV row that merely adopted the id is kept (it's real history) and
    just unlinked. Returns the number of rows deleted."""
    if not plaid_transaction_ids:
        return 0
    db = get_db()
    removed = 0
    for ptid in plaid_transaction_ids:
        victim = db.execute(
            "SELECT id FROM transactions WHERE plaid_transaction_id=? AND raw_csv_row IS NULL",
            (ptid,),
        ).fetchone()
        if victim:
            db.execute("UPDATE outing_line_items SET transaction_id=NULL WHERE transaction_id=?",
                       (victim["id"],))
            db.execute("DELETE FROM transactions WHERE id=?", (victim["id"],))
            removed += 1
        else:
            db.execute("UPDATE transactions SET plaid_transaction_id=NULL WHERE plaid_transaction_id=?",
                       (ptid,))
    db.commit()
    return removed


def get_uncategorized_plaid_ids(plaid_transaction_ids):
    """Freshly synced rows (by plaid_transaction_id) that no rule matched — the
    Plaid analogue of get_uncategorized_by_batch, for handing off to Claude."""
    if not plaid_transaction_ids:
        return []
    placeholders = ",".join("?" * len(plaid_transaction_ids))
    return get_db().execute(
        f"SELECT id, description, category FROM transactions "
        f"WHERE plaid_transaction_id IN ({placeholders}) AND category IS NULL ORDER BY id",
        list(plaid_transaction_ids),
    ).fetchall()


def get_descriptions(ids):
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"SELECT description FROM transactions WHERE id IN ({placeholders})", ids
    ).fetchall()
    return [r[0] for r in rows]

def bulk_set_category(ids, category):
    """Mass-categorize a set of transactions as user-confirmed (never reverted by rule re-apply)."""
    db = get_db()
    db.executemany(
        "UPDATE transactions SET category=?, category_source='user' WHERE id=?",
        [(category, i) for i in ids],
    )
    db.commit()

def update_category(transaction_id, category, source="user"):
    db = get_db()
    db.execute(
        "UPDATE transactions SET category=?, category_source=? WHERE id=?",
        (category, source, transaction_id),
    )
    db.commit()

def bulk_update_category(id_category_pairs, source="claude"):
    db = get_db()
    for tid, cat in id_category_pairs:
        db.execute(
            "UPDATE transactions SET category=?, category_source=? WHERE id=?",
            (cat, source, tid),
        )
    db.commit()

def get_by_id(transaction_id):
    return get_db().execute(
        "SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()

def delete(transaction_id):
    db = get_db()
    # A split line item may reference this transaction — unlink, keep the outing.
    db.execute("UPDATE outing_line_items SET transaction_id=NULL WHERE transaction_id=?",
               (transaction_id,))
    db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
    db.commit()

def get_categories_summary(start_date=None, end_date=None):
    query = "SELECT category, SUM(amount) as total, COUNT(*) as cnt FROM transactions WHERE amount < 0"
    params = []
    if start_date:
        query += " AND date>=?"
        params.append(start_date)
    if end_date:
        query += " AND date<=?"
        params.append(end_date)
    query += " GROUP BY category ORDER BY total ASC"
    return get_db().execute(query, params).fetchall()
