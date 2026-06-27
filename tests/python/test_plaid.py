"""Plaid mapping + dedup. The pure mappers need no DB; the dedup tests run against
the temp DB. No network: services/plaid_api imports the SDK lazily, and these tests
only call the pure functions + the model layer, never the API."""
import pytest

import models.transaction as tx_model
from database.db import get_db
from services import plaid_api


# ----------------------------------------------------------------- pure mappers

def test_map_transaction_flips_sign_and_prefers_merchant():
    txn = {"transaction_id": "p1", "amount": 5.25, "name": "STARBUCKS #1234",
           "merchant_name": "Starbucks", "date": "2026-06-12", "iso_currency_code": "USD"}
    row = plaid_api.map_transaction(txn, account_id=7)
    # Plaid: +amount = money out; we store money-out as negative.
    assert row["amount"] == -5.25
    assert row["description"] == "Starbucks"   # merchant_name preferred over raw name
    assert row["account_id"] == 7
    assert row["plaid_transaction_id"] == "p1"


def test_map_transaction_inflow_is_positive():
    txn = {"transaction_id": "p2", "amount": -100.0, "name": "Payroll", "date": "2026-06-01"}
    assert plaid_api.map_transaction(txn, 1)["amount"] == 100.0


def test_map_account_type():
    assert plaid_api._map_account_type("depository", "checking") == ("checking", 0)
    assert plaid_api._map_account_type("depository", "savings") == ("savings", 0)
    assert plaid_api._map_account_type("credit", "credit card") == ("credit", 1)
    assert plaid_api._map_account_type("loan", "student") == ("loan", 1)
    assert plaid_api._map_account_type("investment", "brokerage") == ("brokerage", 0)
    assert plaid_api._map_account_type("other", None) == ("other", 0)


# --------------------------------------------------------------------- dedup

def _row(ptid, amount, date, desc="Plaid Merchant", account_id=1):
    return {"account_id": account_id, "date": date, "description": desc,
            "amount": amount, "plaid_transaction_id": ptid}


def test_insert_then_resync_is_noop(flask_app):
    with flask_app.app_context():
        rows = [_row("a", -10.0, "2026-06-10"), _row("b", -20.0, "2026-06-11")]
        assert tx_model.insert_plaid_rows(rows) == {"inserted": 2, "updated": 0, "skipped": 0}
        # Re-syncing the same Plaid txns updates in place — never duplicates.
        res = tx_model.insert_plaid_rows(rows)
        assert res == {"inserted": 0, "updated": 2, "skipped": 0}
        assert tx_model.count(None, None, None, None) == 2


def test_cross_source_dedup_against_csv(flask_app):
    with flask_app.app_context():
        # A CSV import already brought this purchase in (raw memo, exact amount).
        tx_model.bulk_insert([{
            "account_id": 1, "date": "2026-06-10",
            "description": "STARBUCKS #1234 SEATTLE WA", "amount": -5.25,
            "raw_csv_row": "{}", "import_batch_id": "csv1",
        }])
        assert tx_model.count(None, None, None, None) == 1

        # Plaid reports the same purchase: clean name, 2 days later (posting lag).
        plaid_row = _row("px", -5.25, "2026-06-12", desc="Starbucks")
        res = tx_model.insert_plaid_rows([plaid_row])
        assert res == {"inserted": 0, "updated": 0, "skipped": 1}
        assert tx_model.count(None, None, None, None) == 1   # no duplicate row

        # The CSV row adopted the Plaid id, so the next sync is a clean no-op.
        adopted = get_db().execute(
            "SELECT plaid_transaction_id, description FROM transactions").fetchone()
        assert adopted["plaid_transaction_id"] == "px"
        assert adopted["description"] == "STARBUCKS #1234 SEATTLE WA"  # CSV row kept

        # A later sync re-sends the same Plaid txn (id now matches directly) — must
        # NOT clobber the CSV's raw description/date with Plaid's cleaned version.
        assert tx_model.insert_plaid_rows([plaid_row])["updated"] == 1
        kept = get_db().execute(
            "SELECT description, date FROM transactions WHERE plaid_transaction_id='px'"
        ).fetchone()
        assert kept["description"] == "STARBUCKS #1234 SEATTLE WA"
        assert kept["date"] == "2026-06-10"


def test_remove_deletes_plaid_origin_but_keeps_csv(flask_app):
    with flask_app.app_context():
        # Pure Plaid row (no raw_csv_row) → removable.
        tx_model.insert_plaid_rows([_row("gone", -9.0, "2026-06-15")])
        # CSV row that adopted a Plaid id → must be kept, just unlinked.
        tx_model.bulk_insert([{
            "account_id": 1, "date": "2026-06-16", "description": "CSV ROW",
            "amount": -7.0, "raw_csv_row": "{}", "import_batch_id": "c"}])
        tx_model.insert_plaid_rows([_row("kept", -7.0, "2026-06-16", desc="Merchant")])

        assert tx_model.remove_plaid_rows(["gone", "kept"]) == 1   # only the pure one
        rows = get_db().execute(
            "SELECT description, plaid_transaction_id FROM transactions ORDER BY id").fetchall()
        assert len(rows) == 1
        assert rows[0]["description"] == "CSV ROW"
        assert rows[0]["plaid_transaction_id"] is None            # unlinked, not deleted


# ----------------------------------------------------------- sandbox reset

def test_reset_sandbox_clears_synced_data_but_keeps_csv(flask_app):
    import models.account as account_model
    import models.plaid_item as item_model
    with flask_app.app_context():
        # An account created by a Plaid link (its own fresh row).
        created_id = account_model.create(
            name="First Platypus Checking", type_="checking", institution="First Platypus",
            external_ref="3710", plaid_account_id="plaid-acct-new", plaid_item_id="item-1")
        item_model.upsert("item-1", "access-tok", "First Platypus Bank")

        # Pure Plaid txns on the created account.
        tx_model.insert_plaid_rows([
            _row("p1", -10.0, "2026-06-10", account_id=created_id),
            _row("p2", -20.0, "2026-06-11", account_id=created_id)])

        # A pre-existing CSV account (seed #1) that gets matched + adopts a Plaid id.
        tx_model.bulk_insert([{
            "account_id": 1, "date": "2026-06-12", "description": "REAL CSV CHARGE",
            "amount": -5.0, "raw_csv_row": "{}", "import_batch_id": "c"}])
        tx_model.insert_plaid_rows([_row("p3", -5.0, "2026-06-12", desc="Clean", account_id=1)])
        account_model.link_plaid(1, "plaid-acct-existing", "item-1")

        summary = plaid_api.reset_sandbox()

        # Two pure-Plaid rows deleted; the adopted CSV row kept but un-stamped.
        assert summary["transactions_deleted"] == 2
        assert summary["transactions_unadopted"] == 1
        # The Plaid-created account is gone; the matched real account stays, unlinked.
        assert "First Platypus Checking" in summary["accounts_deleted"]
        assert account_model.get_by_id(created_id) is None
        kept_acct = account_model.get_by_id(1)
        assert kept_acct is not None and kept_acct["plaid_account_id"] is None
        # The CSV charge survives with its raw description, Plaid id cleared.
        rows = get_db().execute(
            "SELECT description, plaid_transaction_id FROM transactions").fetchall()
        assert [r["description"] for r in rows] == ["REAL CSV CHARGE"]
        assert rows[0]["plaid_transaction_id"] is None
        # Every linked Item dropped.
        assert summary["items_removed"] == 1
        assert item_model.get_all() == []


def test_reset_sandbox_refuses_outside_sandbox(flask_app, monkeypatch):
    import config
    with flask_app.app_context():
        monkeypatch.setattr(config, "PLAID_ENV", "production")
        with pytest.raises(RuntimeError, match="sandbox"):
            plaid_api.reset_sandbox()
