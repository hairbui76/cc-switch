"""The account store: saving, loading and applying accounts.

An account is a single JSON file holding the credentials plus the few keys of
~/.claude.json that identify who is logged in. Nothing else is captured, which
is what makes sessions and settings shared rather than per-account.
"""

import os
import re
import shutil
import sys
from datetime import datetime, timezone

from .credentials import oauth_block, read_credentials, write_credentials
from .jsonio import read_json, write_json
from .paths import (account_path, claude_config_path, config_backup_path,
                    credentials_path, store_dir)
from .term import CliError, dim, warn

STORE_VERSION = 2

# Keys in ~/.claude.json that identify the logged-in account. These are swapped
# on every switch; everything else in the file is shared between accounts.
ACCOUNT_CONFIG_KEYS = (
    "oauthAccount",
    "userID",
    "customApiKeyResponses",
    "cachedUsageUtilization",
    "cachedExtraUsageDisabledReason",
    "overageCreditGrantCache",
    "passesEligibilityCache",
    "modelAccessCache",
    "additionalModelOptionsCache",
    "additionalModelCostsCache",
    "orgModelDefaultCache",
    "metricsStatusCache",
    "groveConfigCache",
    "clientDataCacheSlots",
    "subscriptionNoticeCount",
    "hasAvailableSubscription",
    "claudeCodeFirstTokenDate",
    "isQualifiedForDataSharing",
)


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-.")
    return slug.lower() or "account"


def unique_name(base: str) -> str:
    existing = set(list_accounts())
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


# --------------------------------------------------------------------------
# reading the store
# --------------------------------------------------------------------------

def list_accounts():
    d = store_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        entry[:-5] for entry in os.listdir(d)
        if entry.endswith(".json") and not entry.startswith(".")
    )


def load_account(name: str):
    data = read_json(account_path(name))
    if data is None:
        raise CliError(
            f"account '{name}' not found. Save it with: claude-switch save {name}"
        )
    if data.get("version") != STORE_VERSION:
        raise CliError(
            f"account '{name}' uses the old v1 format. Run: claude-switch migrate"
        )
    return data


def account_summary(data) -> str:
    email = data.get("email") or "?"
    org = data.get("organizationName")
    return f"{email}{dim(' @ ' + org) if org else ''}"


# --------------------------------------------------------------------------
# identifying the live account
# --------------------------------------------------------------------------

def current_account_uuid():
    """UUID of the account currently logged in, read from ~/.claude.json."""
    cfg = read_json(claude_config_path(), {}) or {}
    acct = cfg.get("oauthAccount")
    return acct.get("accountUuid") if isinstance(acct, dict) else None


def find_by_uuid(uuid):
    if not uuid:
        return None
    for name in list_accounts():
        try:
            data = load_account(name)
        except CliError:
            continue
        if data.get("accountUuid") == uuid:
            return name
    return None


def current_account_name():
    return find_by_uuid(current_account_uuid())


# --------------------------------------------------------------------------
# writing the store
# --------------------------------------------------------------------------

def build_account(name: str, creds, cfg):
    """Assemble an account record from credentials + a ~/.claude.json dict."""
    acct = cfg.get("oauthAccount") or {}
    return {
        "version": STORE_VERSION,
        "name": name,
        "savedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "accountUuid": acct.get("accountUuid"),
        "email": acct.get("emailAddress"),
        "organizationName": acct.get("organizationName"),
        "subscriptionType": oauth_block(creds).get("subscriptionType"),
        "credentials": creds,
        "config": {k: cfg[k] for k in ACCOUNT_CONFIG_KEYS if k in cfg},
    }


def save_account(data) -> None:
    write_json(account_path(data["name"]), data, private=True)


def snapshot_current(name: str):
    """Capture the live credentials + identity keys into account `name`."""
    creds = read_credentials()
    if not creds:
        raise CliError(
            "no credentials found - run `claude login` first "
            f"(looked in {credentials_path()}"
            + (" and the macOS Keychain)" if sys.platform == "darwin" else ")")
        )
    data = build_account(name, creds, read_json(claude_config_path(), {}) or {})
    save_account(data)
    return data


def backup_live_config() -> None:
    src = claude_config_path()
    if not os.path.exists(src):
        return
    os.makedirs(store_dir(), exist_ok=True)
    try:
        shutil.copy2(src, config_backup_path())
    except OSError as exc:
        warn(f"could not back up .claude.json: {exc}")


def apply_account(data) -> None:
    """Make `data` the live account: swap credentials + identity keys only."""
    backup_live_config()

    cfg = read_json(claude_config_path(), {}) or {}
    saved_cfg = data.get("config") or {}
    for key in ACCOUNT_CONFIG_KEYS:
        if key in saved_cfg:
            cfg[key] = saved_cfg[key]
        else:
            # Never leave the previous account's value behind.
            cfg.pop(key, None)
    write_json(claude_config_path(), cfg)
    write_credentials(data["credentials"])
