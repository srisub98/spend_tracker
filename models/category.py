from database.db import get_db

def get_all(active_only=True):
    query = "SELECT * FROM categories"
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY sort_order, name"
    return get_db().execute(query).fetchall()

def get_names(active_only=True):
    return [r["name"] for r in get_all(active_only)]

def get_by_kind(kind, active_only=True):
    query = "SELECT * FROM categories WHERE kind=?"
    if active_only:
        query += " AND active=1"
    query += " ORDER BY sort_order, name"
    return get_db().execute(query, (kind,)).fetchall()

def kind_of(name):
    row = get_db().execute("SELECT kind FROM categories WHERE name=?", (name,)).fetchone()
    return row["kind"] if row else None
