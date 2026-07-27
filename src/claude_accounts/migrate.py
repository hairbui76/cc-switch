"""Importing accounts saved by v1 of this tool.

v1 stored a whole copy of ~/.claude per account, which is what caused sessions
to roll back on every switch. Migration keeps the credentials, drops the rest,
and rescues any session that exists only inside a snapshot.
"""

import os
import shutil

from .credentials import oauth_block
from .jsonio import read_json
from .paths import account_path, claude_dir, store_dir
from .store import (ACCOUNT_CONFIG_KEYS, STORE_VERSION, account_summary,
                    build_account, save_account)
from .term import bold, err, info, ok, warn


def _legacy_dirs():
    d = store_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, entry) for entry in os.listdir(d)
        if entry.endswith("-dir") and os.path.isdir(os.path.join(d, entry))
    )


def has_legacy_dirs() -> bool:
    return bool(_legacy_dirs())


def convert_accounts():
    """Rewrite every v1 account file in the current format."""
    d = store_dir()
    migrated, already = [], []

    for entry in sorted(os.listdir(d)):
        if not entry.endswith(".json") or entry.startswith("."):
            continue
        name = entry[:-5]
        raw = read_json(os.path.join(d, entry), {}) or {}
        if raw.get("version") == STORE_VERSION:
            already.append(name)
            continue

        # v1 stored the whole ~/.claude.json, so the identity keys are at the
        # top level and the credentials sit in the sibling snapshot directory.
        creds = read_json(os.path.join(d, name + "-dir", ".credentials.json"))
        if not creds:
            err(f"{name}: no .credentials.json in {name}-dir, cannot migrate")
            continue

        data = build_account(name, creds, raw)
        data["subscriptionType"] = oauth_block(creds).get("subscriptionType")
        data["config"] = {k: raw[k] for k in ACCOUNT_CONFIG_KEYS if k in raw}
        save_account(data)
        migrated.append(name)
        ok(f"migrated {bold(name)}  {account_summary(data)}")

    return migrated, already


def rescue_sessions() -> int:
    """Copy sessions that exist only in a v1 snapshot into the shared dir.

    Existing files are never overwritten.
    """
    shared = os.path.join(claude_dir(), "projects")
    copied = 0

    for legacy in _legacy_dirs():
        source = os.path.join(legacy, "projects")
        if not os.path.isdir(source):
            continue
        for root, _dirs, files in os.walk(source):
            rel = os.path.relpath(root, source)
            target = shared if rel == "." else os.path.join(shared, rel)
            for fname in files:
                dest = os.path.join(target, fname)
                if os.path.exists(dest):
                    continue
                os.makedirs(target, exist_ok=True)
                shutil.copy2(os.path.join(root, fname), dest)
                copied += 1

    return copied


def run() -> int:
    d = store_dir()
    if not os.path.isdir(d):
        warn(f"{d} does not exist - nothing to migrate")
        return 0

    migrated, already = convert_accounts()

    copied = rescue_sessions()
    if copied:
        shared = os.path.join(claude_dir(), "projects")
        ok(f"rescued {copied} session file(s) from v1 snapshots into {shared}")

    if already:
        info(f"already up to date: {', '.join(already)}")
    if not migrated and not already:
        warn("nothing to migrate")
    elif migrated:
        print()
        info(f"v1 snapshots are still at {os.path.join(d, '*-dir')} - "
             "delete them once you have verified every account works")
    return 0


def account_file_is_legacy(name: str) -> bool:
    raw = read_json(account_path(name), {}) or {}
    return raw.get("version") != STORE_VERSION
