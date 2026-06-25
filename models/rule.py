from database.db import get_db

def get_all():
    return get_db().execute(
        "SELECT * FROM rules ORDER BY priority, id"
    ).fetchall()

def get_active():
    return get_db().execute(
        "SELECT * FROM rules WHERE active=1 ORDER BY priority, id"
    ).fetchall()

def create(pattern, category, match_type="substring", priority=100, active=1):
    db = get_db()
    cur = db.execute(
        "INSERT INTO rules (pattern, match_type, category, priority, active) VALUES (?,?,?,?,?)",
        (pattern, match_type, category, priority, active),
    )
    db.commit()
    return cur.lastrowid

def update(rule_id, pattern, category, match_type, priority, active):
    db = get_db()
    db.execute(
        "UPDATE rules SET pattern=?, match_type=?, category=?, priority=?, active=? WHERE id=?",
        (pattern, match_type, category, priority, active, rule_id),
    )
    db.commit()

def delete(rule_id):
    db = get_db()
    db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    db.commit()
