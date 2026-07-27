"""Argument parsing and process entry point."""

import argparse
import os
import sys

from . import VERSION, commands, updater
from .paths import store_dir
from .term import CliError, enable_debug, err

# Anything not in here is treated as an account name, so that
# `claude-switch work` means `claude-switch use work`.
KNOWN_ARGS = {
    "save", "use", "next", "list", "ls", "status", "remove", "rm",
    "usage", "migrate", "sync", "doctor", "update", "version", "setup",
    "help", "-h", "--help", "--version",
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="claude-switch",
        description="Switch between multiple Claude Code accounts. Sessions, "
                    "settings and history are shared by every account.",
        epilog="Shorthand: `claude-switch <name>` is the same as "
               "`claude-switch use <name>`.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {VERSION}")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="trace every HTTP request on stderr "
                             "(or set CLAUDE_SWITCH_DEBUG=1)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("save", help="save the current login as an account")
    p.add_argument("name", nargs="?",
                   help="account name (default: from email)")
    p.set_defaults(func=commands.cmd_save)

    p = sub.add_parser("use", help="switch to an account")
    p.add_argument("name")
    p.set_defaults(func=commands.cmd_switch)

    p = sub.add_parser("next", help="switch to the next account (round-robin)")
    p.set_defaults(func=commands.cmd_next)

    for alias in ("list", "ls"):
        p = sub.add_parser(alias, help="list saved accounts")
        p.set_defaults(func=commands.cmd_list)

    p = sub.add_parser("status", help="show the account currently logged in")
    p.set_defaults(func=commands.cmd_status)

    for alias in ("remove", "rm"):
        p = sub.add_parser(alias, help="delete a saved account")
        p.add_argument("name")
        p.add_argument("--force", action="store_true",
                       help="allow removing the active account")
        p.set_defaults(func=commands.cmd_remove)

    p = sub.add_parser("usage",
                       help="show usage for every account (no switching)")
    p.add_argument("name", nargs="?", help="limit to one account")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=commands.cmd_usage)

    p = sub.add_parser("migrate", help="import accounts saved by v1")
    p.set_defaults(func=commands.cmd_migrate)

    p = sub.add_parser("sync",
                       help="(deprecated) sessions are shared automatically")
    p.set_defaults(func=commands.cmd_sync)

    p = sub.add_parser("doctor",
                       help="diagnose paths, credentials and API access")
    p.set_defaults(func=commands.cmd_doctor)

    p = sub.add_parser("update", help="update to the newest published build")
    p.add_argument("--check", action="store_true",
                   help="report whether an update exists, install nothing")
    p.add_argument("--rollback", action="store_true",
                   help="go back to the previously installed build")
    p.add_argument("--channel", choices=updater.CHANNELS,
                   help="main tracks every push, stable tracks git tags "
                        "(default: whatever was installed)")
    p.add_argument("--force", action="store_true",
                   help="reinstall even when already up to date")
    p.set_defaults(func=commands.cmd_update)

    p = sub.add_parser("version",
                       help="show the installed build, channel and paths")
    p.set_defaults(func=commands.cmd_version)

    p = sub.add_parser("setup",
                       help="rebuild the claude-* launchers and PATH entry")
    p.add_argument("--bootstrap", action="store_true",
                   help=argparse.SUPPRESS)  # used by install.sh / install.ps1
    p.add_argument("--channel", choices=updater.CHANNELS,
                   help=argparse.SUPPRESS)
    p.set_defaults(func=commands.cmd_setup)

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Insert the implicit `use`, skipping any leading global flags so that
    # `claude-switch --debug work` still resolves to an account name.
    first = next((i for i, a in enumerate(argv) if not a.startswith("-")), None)
    if first is not None and argv[first] not in KNOWN_ARGS:
        argv.insert(first, "use")

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.debug:
        enable_debug()
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    os.makedirs(store_dir(), exist_ok=True)
    try:
        return args.func(args)
    except CliError as exc:
        err(str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
