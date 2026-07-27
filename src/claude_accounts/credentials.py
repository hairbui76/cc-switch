"""Reading and writing Claude Code's OAuth credentials.

On most machines these live in ~/.claude/.credentials.json. On macOS they are
usually in the login Keychain instead, so both are supported.
"""

import json
import os
import subprocess
import sys

from .jsonio import read_json, write_json
from .paths import claude_dir, credentials_path
from .term import warn

KEYCHAIN_SERVICE = "Claude Code-credentials"


def _keychain_read():
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", os.environ.get("USER", ""), "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return json.loads(out.stdout.strip())
    except json.JSONDecodeError:
        return None


def _keychain_write(creds) -> bool:
    try:
        out = subprocess.run(
            ["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
             "-a", os.environ.get("USER", ""), "-w", json.dumps(creds)],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def read_credentials():
    """Return the live credentials dict, or None."""
    creds = read_json(credentials_path())
    if creds:
        return creds
    if sys.platform == "darwin":
        return _keychain_read()
    return None


def write_credentials(creds) -> None:
    """Write credentials back to wherever this machine keeps them."""
    if sys.platform == "darwin" and not os.path.exists(credentials_path()):
        if _keychain_write(creds):
            return
        warn("keychain write failed, falling back to ~/.claude/.credentials.json")
    os.makedirs(claude_dir(), exist_ok=True)
    write_json(credentials_path(), creds, private=True)


def oauth_block(creds):
    """The claudeAiOauth sub-object, or {} if absent."""
    if isinstance(creds, dict):
        blk = creds.get("claudeAiOauth")
        if isinstance(blk, dict):
            return blk
    return {}
