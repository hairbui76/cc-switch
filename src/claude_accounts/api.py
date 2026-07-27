"""Talking to Anthropic's OAuth endpoints.

Usage is read straight from the API using each account's stored token, so
reporting on every account needs no switching at all.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from .credentials import oauth_block, read_credentials, write_credentials
from .store import current_account_uuid, save_account
from .term import CliError, debug, dim, green, red, yellow

OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
API_BASE = "https://api.anthropic.com"
USAGE_URL = f"{API_BASE}/api/oauth/usage"
TOKEN_URL = f"{API_BASE}/v1/oauth/token"
USER_AGENT = "claude-cli/2.1.216 (external, cli)"

# Refresh a little early so a token cannot expire mid-request.
EXPIRY_MARGIN_MS = 60_000


class ApiError(CliError):
    """An HTTP call failed. Carries enough context to say *which* one."""

    def __init__(self, message, stage=None, url=None, status=None, body=None):
        super().__init__(message)
        self.stage = stage
        self.url = url
        self.status = status
        self.body = body


def _explain(stage: str, status: int, body: str) -> str:
    """Turn an HTTP failure into something the user can act on."""
    try:
        parsed = json.loads(body)
        error = parsed.get("error")
        detail = (parsed.get("error_description")
                  or (error.get("message") if isinstance(error, dict) else "")
                  or (error if isinstance(error, str) else "")
                  or "")
    except (ValueError, AttributeError):
        detail = body.strip()[:120]

    if stage == "refresh" and status in (400, 401):
        return "refresh token rejected - log in again on this account"
    if stage == "usage" and status == 401:
        return "token rejected - log in again on this account"
    if status == 429:
        return "rate limited - try again shortly"

    return f"{stage}: HTTP {status}{' - ' + detail if detail else ''}"


def http_json(url: str, token=None, payload=None, timeout: int = 20,
              stage: str = "request"):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["anthropic-beta"] = "oauth-2025-04-20"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    debug(f"{'POST' if body else 'GET '} {url}  ({stage})")
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            debug(f"  -> {resp.status} {len(text)}B")
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        debug(f"  -> {exc.code} {text[:400]}")
        raise ApiError(_explain(stage, exc.code, text),
                       stage=stage, url=url, status=exc.code, body=text)
    except urllib.error.URLError as exc:
        debug(f"  -> network error: {exc.reason}")
        raise ApiError(f"{stage}: network error - {exc.reason}",
                       stage=stage, url=url)


def refresh_tokens(blk):
    """Exchange a refresh token for a new access token. Returns a new block."""
    refresh = blk.get("refreshToken")
    if not refresh:
        raise CliError("no refresh token stored - log in again")

    data = http_json(TOKEN_URL, stage="refresh", payload={
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


def _fresh(blk) -> bool:
    expires_at = blk.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return False
    return expires_at > time.time() * 1000 + EXPIRY_MARGIN_MS


def token_for(data):
    """A usable access token, refreshed and persisted if it has expired."""
    is_current = data.get("accountUuid") == current_account_uuid()

    # Claude Code refreshes the live credentials on its own, so for the active
    # account they are at least as fresh as our stored copy - and often newer.
    if is_current:
        live = oauth_block(read_credentials())
        if live.get("accessToken") and _fresh(live):
            debug(f"{data.get('name')}: using live credentials")
            return live["accessToken"]

    blk = oauth_block(data.get("credentials"))
    if not blk.get("accessToken"):
        raise CliError("no access token stored - log in again")
    if _fresh(blk):
        debug(f"{data.get('name')}: stored token still valid")
        return blk["accessToken"]

    debug(f"{data.get('name')}: token expired, refreshing")
    creds = dict(data.get("credentials") or {})
    creds["claudeAiOauth"] = refresh_tokens(blk)
    data["credentials"] = creds
    save_account(data)
    if is_current:
        write_credentials(creds)
    return creds["claudeAiOauth"]["accessToken"]


def fetch_usage(token):
    return http_json(USAGE_URL, token=token, stage="usage")


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
