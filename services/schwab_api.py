"""
Schwab Trader API client (PRD Phase 4b) — free official individual-developer API.

Setup (one-time, see README):
  1. Register at developer.schwab.com, create an app with the "Accounts and Trading
     Production" product and callback URL exactly `https://127.0.0.1`.
  2. Wait for the app to show "Ready for use" (can take days).
  3. Put SCHWAB_APP_KEY / SCHWAB_APP_SECRET in .env.

Auth model: OAuth2 with a paste-the-redirect flow (no local HTTPS listener needed):
the user opens the authorize URL, logs in, lands on https://127.0.0.1/?code=...
(browser shows a connection error — that's fine), and pastes the full address bar
URL back into the app. Access tokens last ~30 min (auto-refreshed); refresh tokens
last 7 days, so expect a weekly re-connect.

Output of fetch_sections() matches services/holdings_parser.py sections, so the
sync writes through the exact same upsert_snapshot/replace_holdings path as CSVs.
"""

import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs

import requests

import config
from database.db import get_db

AUTH_BASE = "https://api.schwabapi.com/v1/oauth"
API_BASE = "https://api.schwabapi.com/trader/v1"

# Schwab instrument assetType -> our holdings.asset_type
ASSET_TYPE_MAP = {
    "EQUITY": "equity",
    "COLLECTIVE_INVESTMENT": "etf",
    "MUTUAL_FUND": "mutual_fund",
    "CASH_EQUIVALENT": "cash",
    "FIXED_INCOME": "other",
}


class SchwabAuthError(Exception):
    """Raised when (re)connecting via the authorize URL is required."""


def configured():
    return bool(config.SCHWAB_APP_KEY and config.SCHWAB_APP_SECRET)


def auth_url():
    return f"{AUTH_BASE}/authorize?" + urlencode({
        "client_id": config.SCHWAB_APP_KEY,
        "redirect_uri": config.SCHWAB_CALLBACK_URL,
    })


def status():
    """None if never connected, else dict with refresh-token expiry info."""
    row = get_db().execute("SELECT * FROM schwab_tokens WHERE id=1").fetchone()
    if not row or not row["refresh_token"]:
        return None
    expires = datetime.fromisoformat(row["refresh_expires_at"])
    return {
        "updated_at": row["updated_at"],
        "refresh_expires_at": row["refresh_expires_at"],
        "days_left": max(0, (expires - datetime.now()).days),
        "expired": datetime.now() >= expires,
    }


def _basic_auth_header():
    raw = f"{config.SCHWAB_APP_KEY}:{config.SCHWAB_APP_SECRET}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode(),
            "Content-Type": "application/x-www-form-urlencoded"}


def _save_tokens(payload):
    now = datetime.now()
    db = get_db()
    db.execute(
        """INSERT INTO schwab_tokens (id, access_token, refresh_token, access_expires_at,
                                      refresh_expires_at, updated_at)
           VALUES (1,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET access_token=excluded.access_token,
               refresh_token=excluded.refresh_token,
               access_expires_at=excluded.access_expires_at,
               refresh_expires_at=excluded.refresh_expires_at,
               updated_at=excluded.updated_at""",
        (payload["access_token"], payload["refresh_token"],
         (now + timedelta(seconds=payload.get("expires_in", 1800) - 60)).isoformat(),
         (now + timedelta(days=7)).isoformat(),  # Schwab refresh tokens live 7 days
         now.isoformat()))
    db.commit()


def exchange_redirect_url(pasted_url):
    """Complete the OAuth flow from the pasted https://127.0.0.1/?code=... URL."""
    qs = parse_qs(urlparse(pasted_url.strip()).query)
    code = (qs.get("code") or [None])[0]
    if not code:
        raise SchwabAuthError("No ?code= found in that URL — paste the full address "
                              "bar contents from the https://127.0.0.1 page.")
    resp = requests.post(f"{AUTH_BASE}/token", headers=_basic_auth_header(), data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.SCHWAB_CALLBACK_URL,
    }, timeout=30)
    if resp.status_code != 200:
        raise SchwabAuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]} "
                              "— note the code expires ~30s after login, paste quickly.")
    _save_tokens(resp.json())


def _access_token():
    row = get_db().execute("SELECT * FROM schwab_tokens WHERE id=1").fetchone()
    if not row or not row["refresh_token"]:
        raise SchwabAuthError("Not connected to Schwab yet.")
    if datetime.now() >= datetime.fromisoformat(row["refresh_expires_at"]):
        raise SchwabAuthError("Schwab refresh token expired (they last 7 days) — reconnect.")
    if datetime.now() < datetime.fromisoformat(row["access_expires_at"]):
        return row["access_token"]
    resp = requests.post(f"{AUTH_BASE}/token", headers=_basic_auth_header(), data={
        "grant_type": "refresh_token",
        "refresh_token": row["refresh_token"],
    }, timeout=30)
    if resp.status_code != 200:
        raise SchwabAuthError(f"Token refresh failed ({resp.status_code}) — reconnect.")
    payload = resp.json()
    payload.setdefault("refresh_token", row["refresh_token"])
    _save_tokens(payload)
    return payload["access_token"]


def fetch_sections():
    """GET /accounts?fields=positions → holdings sections (same shape as the CSV
    parser): [{institution, account_ref, positions: [...], total}]."""
    token = _access_token()
    resp = requests.get(f"{API_BASE}/accounts", params={"fields": "positions"},
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code == 401:
        raise SchwabAuthError("Schwab rejected the token — reconnect.")
    resp.raise_for_status()
    return [map_account(a) for a in resp.json()]


def map_account(payload):
    """Map one Schwab /accounts entry to a holdings section. Pure function — unit-testable."""
    acct = payload.get("securitiesAccount", payload)
    balances = acct.get("currentBalances", {})
    positions = []
    for p in acct.get("positions", []):
        inst = p.get("instrument", {})
        qty = (p.get("longQuantity") or 0) - (p.get("shortQuantity") or 0)
        value = p.get("marketValue")
        if value is None:
            continue
        avg_price = p.get("averagePrice")
        asset_type = ASSET_TYPE_MAP.get(inst.get("assetType"), "other")
        positions.append({
            "symbol": inst.get("symbol"),
            "description": inst.get("description") or inst.get("symbol") or "",
            "quantity": qty or None,
            "price": (value / qty) if qty else None,
            "market_value": value,
            "asset_type": asset_type,
            "cost_basis": (avg_price * qty) if (avg_price and qty) else None,
        })
    # Sweep cash isn't a position — add it from balances
    cash = balances.get("cashBalance") or 0
    if cash:
        positions.append({
            "symbol": None, "description": "Cash & Cash Investments",
            "quantity": None, "price": None, "market_value": cash,
            "asset_type": "cash", "cost_basis": None,
        })
    return {
        "institution": "Schwab",
        "account_ref": str(acct.get("accountNumber", "")),
        "positions": positions,
        "total": balances.get("liquidationValue"),
    }
