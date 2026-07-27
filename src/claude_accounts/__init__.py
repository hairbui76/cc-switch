"""Claude Code Multi-Account Switcher.

Only the *credentials* are per-account. Everything else in ~/.claude
(projects, sessions, history, settings, todos, plugins) stays in place and is
therefore shared by every account automatically.
"""

VERSION = "2.0.0"

__all__ = ["VERSION"]
