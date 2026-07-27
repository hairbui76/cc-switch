"""Claude Code Multi-Account Switcher.

Only the *credentials* are per-account. Everything else in ~/.claude
(projects, sessions, history, settings, todos, plugins) stays in place and is
therefore shared by every account automatically.
"""

import os


def _read_version() -> str:
    """The version string, read from the repo-root VERSION file.

    Kept in a plain file rather than hard-coded here so `claude-switch update`
    can learn the published version from a single raw URL, without downloading
    and unpacking a whole tree just to compare.
    """
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(root, "VERSION"), "r", encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


VERSION = _read_version()

__all__ = ["VERSION"]
