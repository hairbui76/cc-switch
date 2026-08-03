"""Where Claude Code and this tool keep their files.

Resolved lazily on every call so tests (and users) can redirect them with
CLAUDE_CONFIG_DIR / CLAUDE_ACCOUNTS_DIR at any point.
"""

import os


def claude_dir() -> str:
    """Claude Code's data directory."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), ".claude")


def claude_config_path() -> str:
    """Claude Code's ~/.claude.json (moves inside CLAUDE_CONFIG_DIR when set)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return os.path.join(claude_dir(), ".claude.json")
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def credentials_path() -> str:
    return os.path.join(claude_dir(), ".credentials.json")


def store_dir() -> str:
    """Where this tool keeps saved accounts."""
    override = os.environ.get("CLAUDE_ACCOUNTS_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), ".claude-accounts")


def account_path(name: str) -> str:
    return os.path.join(store_dir(), name + ".json")


def config_backup_path() -> str:
    return os.path.join(store_dir(), ".claude.json.bak")


def profiles_dir() -> str:
    """Parent of the per-account config directories used by `cc run`."""
    return os.path.join(store_dir(), "profiles")


def profile_dir(name: str) -> str:
    return os.path.join(profiles_dir(), name)


def bindings_path() -> str:
    """Which directory runs under which account.

    A dotfile so `list_accounts`, which treats every *.json in the store as an
    account, does not offer "bindings" as one.
    """
    return os.path.join(store_dir(), ".bindings.json")
