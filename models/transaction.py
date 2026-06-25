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
