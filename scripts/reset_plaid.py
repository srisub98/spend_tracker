"""Admin: reset Plaid sync state for sandbox re-testing.

Deletes Plaid-synced transactions, removes Plaid-created accounts (keeps and unlinks any
pre-existing account that was matched by last-4), and drops every linked Item — so the
sandbox link/sync flow can be run again from a clean slate. Refuses unless
PLAID_ENV=sandbox, so it can never wipe production-synced data.

    python3 scripts/reset_plaid.py          # shows what it found, then prompts
    python3 scripts/reset_plaid.py --yes    # no prompt (used by `make plaid-reset`)

Honors DB_PATH from the environment, like the other admin scripts.
"""
import os
import sys
import argparse

# Run as a script (python scripts/reset_plaid.py) — put the repo root, not scripts/,
# at the front of sys.path so `import app` / `import config` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    import config
    from app import app
    from database.db import init_db, get_db
    from services import plaid_api

    init_db(app)
    with app.app_context():
        if not plaid_api.is_sandbox():
            sys.exit(f"Refusing: PLAID_ENV={config.PLAID_ENV!r} is not 'sandbox'. "
                     "This tool only resets sandbox data.")

        db = get_db()
        n_tx = db.execute("SELECT COUNT(*) FROM transactions "
                          "WHERE plaid_transaction_id IS NOT NULL").fetchone()[0]
        n_acct = db.execute("SELECT COUNT(*) FROM accounts "
                            "WHERE plaid_account_id IS NOT NULL").fetchone()[0]
        n_item = db.execute("SELECT COUNT(*) FROM plaid_items").fetchone()[0]
        if not (n_tx or n_acct or n_item):
            print("Nothing to reset — no Plaid data found.")
            return
        print(f"[DB: {config.DB_PATH}] Found {n_tx} Plaid-synced transactions, "
              f"{n_acct} linked accounts, {n_item} item(s).")

        if not args.yes:
            if input("Reset all of it? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return

        s = plaid_api.reset_sandbox()
        print("Done. "
              f"{s['transactions_deleted']} transactions deleted"
              + (f", {s['transactions_unadopted']} CSV rows un-linked"
                 if s['transactions_unadopted'] else "")
              + f", {len(s['accounts_deleted'])} accounts removed"
              + (f" ({', '.join(s['accounts_deleted'])})" if s['accounts_deleted'] else "")
              + (f", {len(s['accounts_unlinked'])} kept+unlinked"
                 if s['accounts_unlinked'] else "")
              + f", {s['items_removed']} item(s) dropped.")


if __name__ == "__main__":
    main()
