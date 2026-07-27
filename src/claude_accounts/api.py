"""Talking to Anthropic's OAuth endpoints.

Usage is read straight from the API using each account's stored token, so
reporting on every account needs no switching at all.
"""

import json
import time
import urllib.request
from datetime import datetime

from .credentials import oauth_block, write_credentials
from .store import current_account_uuid, save_account
from .term import CliError, dim, green, red, yellow

OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
API_BASE = "https://api.anthropic.com"
USAGE_URL = f"{API_BASE}/api/oauth/usage"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
USER_AGENT = "claude-cli/2.1.216 (external, cli)"

# Refresh a little early so a token cannot expire mid-request.
EXPIRY_MARGIN_MS = 60_000


def http_json(url: str, token=None, payload=None, timeout: int = 20):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["anthropic-beta"] = "oauth-2025-04-20"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_tokens(blk):
    """Exchange a refresh token for a new access token. Returns a new block."""
    refresh = blk.get("refreshToken")
    if not refresh:
        raise CliError("no refresh token stored")
    data = http_json(TOKEN_URL, payload={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": OAUTH_CLIENT_ID,
    })
    new = dict(blk)
    new["accessToken"] = data["access_token"]
    if data.get("refresh_token"):
        new["refreshToken"] = data["refresh_token"]
    if data.get("expires_in"):
        expires_in_ms = int(data["expires_in"]) * 1000
        new["expiresAt"] = int(time.time() * 1000) + expires_in_ms
    return new


def token_for(data):
    """A usable access token, refreshed and persisted if it has expired."""
    blk = oauth_block(data.get("credentials"))
    token = blk.get("accessToken")
    if not token:
        raise CliError("no access token stored")

    expires_at = blk.get("expiresAt")
    deadline = time.time() * 1000 + EXPIRY_MARGIN_MS
    if isinstance(expires_at, (int, float)) and expires_at > deadline:
        return token

    creds = dict(data.get("credentials") or {})
    creds["claudeAiOauth"] = refresh_tokens(blk)
    data["credentials"] = creds
    save_account(data)
    # Keep the live credentials in sync when this is the active account.
    if data.get("accountUuid") == current_account_uuid():
        write_credentials(creds)
    return creds["claudeAiOauth"]["accessToken"]


def fetch_usage(token):
    return http_json(USAGE_URL, token=token)


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def fmt_reset(iso) -> str:
    """'Tue 00:50 (3h33m)' for an ISO-8601 reset timestamp."""
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return str(iso)

    minutes = int((when - datetime.now().astimezone()).total_seconds() // 60)
    if minutes < 0:
        return "now"
    if minutes < 60:
        rel = f"{minutes}m"
    elif minutes < 60 * 24:
        rel = f"{minutes // 60}h{minutes % 60:02d}m"
    else:
        rel = f"{minutes // 1440}d{(minutes % 1440) // 60}h"
    return f"{when.strftime('%a %H:%M')} ({rel})"


def fmt_pct(block) -> str:
    """A colour-coded utilisation percentage."""
    if not isinstance(block, dict) or block.get("utilization") is None:
        return dim("  -%")
    pct = int(round(float(block["utilization"])))
    text = f"{pct:3d}%"
    if pct >= 90:
        return red(text)
    if pct >= 70:
        return yellow(text)
    return green(text)
