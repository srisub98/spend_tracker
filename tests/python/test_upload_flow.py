"""End-to-end upload via the Flask test client: preview -> confirm -> dedup."""
import io


def _preview(client, fixtures_dir, name, account_id):
    data = {
        "account_id": str(account_id),
        "csv_file": (io.BytesIO((fixtures_dir / name).read_bytes()), name),
    }
    return client.post("/transactions/upload", data=data, content_type="multipart/form-data")


def _confirm(client, name, account_id):
    return client.post(
        "/transactions/upload/confirm",
        data={"account_id": str(account_id), "filename": name},
        follow_redirects=True,
    )


def _count(flask_app):
    import models.transaction as tx
    with flask_app.app_context():
        return tx.count(None, None, None, None)


def test_preview_confirm_then_reupload_dedups(client, flask_app, fixtures_dir):
    r = _preview(client, fixtures_dir, "citi-checking.csv", account_id=1)
    assert r.status_code == 200
    assert b"4 rows parsed" in r.data            # preview, nothing inserted yet
    assert _count(flask_app) == 0

    _confirm(client, "citi-checking.csv", account_id=1)
    assert _count(flask_app) == 4

    # Re-importing the same file is safe — UNIQUE(account,date,desc,amount) dedups.
    _confirm(client, "citi-checking.csv", account_id=1)
    assert _count(flask_app) == 4


def test_uncategorized_rows_land_in_review(client, flask_app, fixtures_dir):
    _preview(client, fixtures_dir, "unmatched.csv", account_id=2)
    _confirm(client, "unmatched.csv", account_id=2)
    r = client.get("/transactions/review")
    assert b"QZX MERCHANT 4471" in r.data
    assert b"NORTHSIDE GENERAL STORE" in r.data
