"""Plaid client — optional bank/credit transaction sync.

Everything here is gated behind configured(): with PLAID_CLIENT_ID / PLAID_SECRET
unset, no route calls into this module and the app is CSV-only, exactly as before.

The plaid SDK is imported lazily inside functions so the app (and the hermetic test
suite) boots fine without the package installed and without ever hitting the network.
map_transaction() and _map_account_type() are pure — unit-testable on plain dicts,
mirroring services/schwab_api.map_account.

Flow: create_link_token() → (browser Plaid Link) → exchange_public_token() stores the
Item and auto-creates/links local accounts → sync_transactions() pulls incrementally
via the /transactions/sync cursor. No webhooks (local app) — sync is a manual button.
"""
import config
import models.account as account_model
import models.plaid_item as item_model
import models.transaction as tx_model


def configured():
    return bool(config.PLAID_CLIENT_ID and config.PLAID_SECRET)


def is_sandbox():
    return (config.PLAID_ENV or "sandbox").lower() == "sandbox"


def reset_sandbox():
    """Admin: wipe all Plaid sync state so the sandbox can be re-tested from a clean
    slate. Refuses unless PLAID_ENV is 'sandbox' — it must never touch production-synced
    data. Deletes Plaid-origin transactions (un-adopting any CSV rows that borrowed an
    id), removes Plaid-created accounts (keeps + unlinks pre-existing matched ones), and
    drops every linked Item. Returns a summary dict."""
    if not is_sandbox():
        raise RuntimeError(
            f"reset_sandbox refused: PLAID_ENV={config.PLAID_ENV!r} is not 'sandbox'.")
    tx = tx_model.delete_plaid_synced()
    accts = account_model.purge_plaid_links()
    items = item_model.delete_all()
    return {
        "transactions_deleted": tx["deleted"],
        "transactions_unadopted": tx["unadopted"],
        "accounts_deleted": accts["deleted"],
        "accounts_unlinked": accts["unlinked"],
        "items_removed": items,
    }


def _client():
    import plaid
    from plaid.api import plaid_api
    host = {
        "sandbox": plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
    }.get((config.PLAID_ENV or "sandbox").lower(), plaid.Environment.Sandbox)
    configuration = plaid.Configuration(
        host=host,
        api_key={"clientId": config.PLAID_CLIENT_ID, "secret": config.PLAID_SECRET},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


# ----------------------------------------------------------------------------- Link

def create_link_token():
    """A short-lived link_token the browser hands to Plaid Link to start the flow."""
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    req = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id="local-single-user"),
        client_name="Finance Tracker",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    return _client().link_token_create(req).link_token


def sandbox_public_token():
    """Sandbox-only shortcut that skips the Link UI entirely — used to verify the
    end-to-end sync without real bank credentials. Uses the dynamic-transactions
    test user so there's realistic, refreshable history."""
    from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
    from plaid.model.sandbox_public_token_create_request_options import (
        SandboxPublicTokenCreateRequestOptions,
    )
    from plaid.model.products import Products
    req = SandboxPublicTokenCreateRequest(
        institution_id="ins_109508",  # First Platypus Bank (sandbox non-OAuth)
        initial_products=[Products("transactions")],
        options=SandboxPublicTokenCreateRequestOptions(
            override_username="user_transactions_dynamic"),
    )
    return _client().sandbox_public_token_create(req).public_token


def exchange_public_token(public_token):
    """Swap the browser's public_token for a durable access_token, persist the Item,
    and auto-create/link the local accounts it exposes. Returns the item_id."""
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    resp = _client().item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token))
    institution = _institution_name(resp.access_token)
    item_model.upsert(resp.item_id, resp.access_token, institution)
    _ensure_accounts(resp.access_token, resp.item_id, institution)
    return resp.item_id


def _institution_name(access_token):
    try:
        from plaid.model.item_get_request import ItemGetRequest
        from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
        from plaid.model.country_code import CountryCode
        client = _client()
        inst_id = client.item_get(ItemGetRequest(access_token=access_token)).item.institution_id
        if not inst_id:
            return None
        return client.institutions_get_by_id(InstitutionsGetByIdRequest(
            institution_id=inst_id, country_codes=[CountryCode("US")])).institution.name
    except Exception:
        return None


# ------------------------------------------------------------------------- Accounts

def _map_account_type(plaid_type, plaid_subtype):
    """Plaid (type, subtype) → our accounts.type + is_liability. Pure."""
    ptype = str(plaid_type or "").lower()
    subtype = str(plaid_subtype or "").lower()
    if ptype == "depository":
        return ("savings" if "savings" in subtype else "checking"), 0
    if ptype == "credit":
        return "credit", 1
    if ptype == "loan":
        return "loan", 1
    if ptype == "investment":
        return "brokerage", 0
    return "other", 0


def _digits(s):
    return "".join(c for c in (s or "") if c.isdigit())


def _match_by_mask(mask, accounts):
    """Reuse the net-worth last-4 matching idea: link a Plaid account to a pre-existing
    CSV account whose external_ref matches its mask."""
    m = _digits(mask)
    if not m:
        return None
    for a in accounts:
        ext = _digits(a["external_ref"])
        if ext and len(ext) >= 3 and (m.endswith(ext) or ext.endswith(m)):
            return a
    return None


def _ensure_accounts(access_token, item_id, institution):
    """For each Plaid account: skip if already linked, else link a matching CSV
    account by last-4, else create a fresh local account."""
    from plaid.model.accounts_get_request import AccountsGetRequest
    accts = _client().accounts_get(AccountsGetRequest(access_token=access_token)).accounts
    existing = account_model.get_all()
    for a in accts:
        if account_model.get_by_plaid_account_id(a.account_id):
            continue
        matched = _match_by_mask(a.mask, existing)
        if matched and not matched["plaid_account_id"]:
            account_model.link_plaid(matched["id"], a.account_id, item_id)
            continue
        type_, is_liab = _map_account_type(a.type, a.subtype)
        account_model.create(
            name=a.name or institution or "Plaid Account",
            type_=type_, institution=institution or "",
            is_liability=is_liab, external_ref=a.mask,
            plaid_account_id=a.account_id, plaid_item_id=item_id,
        )


# --------------------------------------------------------------------- Transactions

def sync_transactions(item):
    """Pull added/modified/removed for one Item via the cursor, paging until done.
    Returns (added, modified, removed_ids, next_cursor). added/modified are plain
    dicts (txn.to_dict()); removed_ids are Plaid transaction_id strings."""
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    client = _client()
    cursor = item["cursor"] or ""
    added, modified, removed = [], [], []
    has_more = True
    while has_more:
        kwargs = {"access_token": item["access_token"]}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.transactions_sync(TransactionsSyncRequest(**kwargs))
        added.extend(t.to_dict() for t in resp.added)
        modified.extend(t.to_dict() for t in resp.modified)
        removed.extend(r.transaction_id for r in resp.removed)
        has_more = resp.has_more
        cursor = resp.next_cursor
    return added, modified, removed, cursor


def map_transaction(txn, account_id):
    """One Plaid transaction dict → a row dict for models.transaction.insert_plaid_rows.
    Pure (no SDK, no DB). Plaid amounts are positive when money LEAVES the account; we
    store positive = money in, so the sign is flipped."""
    amount = -round(float(txn["amount"]), 2)
    name = (txn.get("merchant_name") or txn.get("name") or "").strip()
    return {
        "account_id": account_id,
        "date": str(txn.get("date")),
        "description": name,
        "amount": amount,
        "currency": txn.get("iso_currency_code") or "USD",
        "plaid_transaction_id": txn["transaction_id"],
    }


def status():
    """UI summary: one entry per active linked Item."""
    return [
        {"item_id": i["item_id"], "institution": i["institution"] or "Linked bank",
         "updated_at": i["updated_at"], "synced": bool(i["cursor"])}
        for i in item_model.get_all()
    ]
