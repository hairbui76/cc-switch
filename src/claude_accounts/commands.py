"""One function per subcommand. All of them return a process exit code."""

import contextlib
import os
import shutil
import sys
import time

from . import bindings, migrate, profiles, shims, updater
from .api import (OAUTH_CLIENT_ID, TOKEN_URL, USAGE_URL, ApiError, fetch_usage,
                  fmt_pct, fmt_reset, http_json, token_for)
from .credentials import oauth_block, read_credentials
from .jsonio import read_json
from .paths import (account_path, claude_config_path, claude_dir,
                    credentials_path, profile_dir, profiles_dir, store_dir)
from .store import (account_summary, current_account_name,
                    current_account_uuid, find_by_uuid, list_accounts,
                    load_account, apply_account, save_account, slugify,
                    snapshot_current, unique_name)
from .term import (CliError, bold, dim, green, info, ok, pad, red, warn,
                   yellow)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _logged_in_email():
    cfg = read_json(claude_config_path(), {}) or {}
    return (cfg.get("oauthAccount") or {}).get("emailAddress")


def autosave_current():
    """Refresh the stored copy of whatever account is live right now.

    Tokens rotate constantly, so the backup would go stale without this. An
    account that was never saved is stored under a name derived from its email
    rather than being discarded.
    """
    uuid = current_account_uuid()
    if not uuid:
        return None

    name = find_by_uuid(uuid)
    if name:
        try:
            snapshot_current(name)
            info(f"auto-saved current account {bold(name)}")
        except CliError as exc:
            warn(f"could not auto-save current account: {exc}")
        return name

    email = _logged_in_email() or ""
    derived = unique_name(slugify(email.split("@")[0]) if email else "unsaved")
    try:
        snapshot_current(derived)
        warn(f"current login was not saved - stored it as {bold(derived)}")
    except CliError:
        warn("current login is not saved and has no credentials to store")
        return None
    return derived


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_save(args):
    name = args.name
    if not name:
        email = _logged_in_email()
        if not email:
            raise CliError(
                "not logged in - run `claude login`, "
                "or pass a name explicitly"
            )
        name = slugify(email.split("@")[0])
        info(f"no name given, using {bold(name)} (from {email})")

    data = snapshot_current(name)
    ok(f"saved {bold(name)}  {account_summary(data)}")
    return 0


def cmd_switch(args):
    target = load_account(args.name)
    if target.get("accountUuid") == current_account_uuid():
        ok(f"already on {bold(args.name)}  {account_summary(target)}")
        return 0

    autosave_current()
    apply_account(target)
    ok(f"switched to {bold(args.name)}  {account_summary(target)}")
    info("sessions and settings are shared - nothing else to sync")
    return 0


def cmd_next(args):
    names = list_accounts()
    if not names:
        raise CliError("no accounts saved yet. Run: "
                       f"{shims.command_name()} save <name>")
    if len(names) == 1:
        ok(f"only one account ({bold(names[0])})")
        return 0

    current = current_account_name()
    index = names.index(current) if current in names else -1
    target = names[(index + 1) % len(names)]

    args.name = target
    code = cmd_switch(args)
    position = names.index(target) + 1
    print(dim(f"     position {position}/{len(names)}"))
    return code


# --------------------------------------------------------------------------
# per-directory accounts
# --------------------------------------------------------------------------

def _resolve_for(where, override=None):
    """The account a directory should run as, and where that came from."""
    if override:
        return override, "argument", None
    name, source, origin = bindings.resolve(where)
    if not name:
        raise CliError(
            f"{where} is not bound to an account. Bind it with: "
            f"{shims.command_name()} bind <name>   (or pass --account)"
        )
    return name, source, origin


def _origin_note(source, origin) -> str:
    if not origin:
        return ""
    return dim(f"  ({source}: {origin})")


def cmd_bind(args):
    name = args.name or current_account_name()
    if not name:
        raise CliError(
            "no account given, and the login in use is not saved. Run: "
            f"{shims.command_name()} bind <name>"
        )

    data = load_account(name)
    path = bindings.bind(args.path or os.getcwd(), name)
    profiles.ensure_profile(data)

    ok(f"{path} -> {bold(name)}  {account_summary(data)}")
    info(f"start Claude Code here with `{shims.command_name()} run`")
    return 0


def cmd_unbind(args):
    path = args.path or os.getcwd()
    name = bindings.unbind(path)
    if not name:
        inherited, source, origin = bindings.resolve(path)
        if inherited:
            raise CliError(
                f"{path} has no binding of its own - it inherits "
                f"{inherited} from {origin}"
            )
        raise CliError(f"{path} is not bound to an account")

    ok(f"unbound {path}  {dim('(was ' + name + ')')}")
    info(f"the profile is kept - remove it with "
         f"`{shims.command_name()} remove {name}`")
    return 0


def cmd_bindings(args):
    entries = bindings.read_bindings()
    active, source, origin = bindings.resolve()

    if not entries:
        warn("no directories bound yet. In a repository, run: "
             f"{shims.command_name()} bind <name>")
    else:
        width = max(len(path) for path in entries)
        print(bold(f"  {'DIRECTORY'.ljust(width)}  ACCOUNT"))
        for path, name in entries.items():
            here = (source == "binding" and origin == path)
            marker = green("*") if here else " "
            print(f"{marker} {path.ljust(width)}  "
                  f"{bold(name) if here else name}")
        print()

    if active:
        print(f"{green('[ok]')} here: {bold(active)}"
              f"{_origin_note(source, origin)}")
    else:
        info(f"{os.getcwd()} is not bound - it would use the live account "
             f"({current_account_name() or 'unsaved'})")
    return 0


def cmd_run(args):
    argv = list(args.argv or [])
    # `cc run -- --resume` and `cc run --resume` mean the same thing; the
    # separator is only there for anyone who wants to be explicit.
    if argv and argv[0] == "--":
        argv.pop(0)

    name, source, origin = _resolve_for(os.getcwd(), args.account)
    data = load_account(name)
    info(f"{bold(name)}  {account_summary(data)}"
         f"{_origin_note(source, origin)}")
    return profiles.launch(data, argv)


def _default_shell() -> str:
    """The syntax the calling shell most likely speaks."""
    if os.name != "nt" or os.environ.get("MSYSTEM") or os.environ.get("SHELL"):
        return "posix"
    return "powershell"


def cmd_env(args):
    if getattr(args, "if_bound", False):
        # An unbound directory is a normal state, not a failure. Callers that
        # run this unconditionally on every launch -- agent-of-empires'
        # `host_hooks.before_session`, a shell hook like direnv -- would
        # otherwise abort on any directory the user never bound. A broken
        # account or profile still raises, so only "no binding here" is
        # softened.
        name = args.account or bindings.resolve(os.getcwd())[0]
        if not name:
            return 0
    else:
        name, _, _ = _resolve_for(os.getcwd(), args.account)
    data = load_account(name)

    # Building the profile can have something to say, and this output is meant
    # to be eval'd - so let it say it on stderr.
    with contextlib.redirect_stdout(sys.stderr):
        lines = profiles.env_exports(data, args.format or _default_shell())
    print("\n".join(lines))
    return 0


def cmd_list(args):
    names = list_accounts()
    if not names:
        warn("no accounts saved yet. Run: "
             f"{shims.command_name()} save <name>")
        return 0

    current = current_account_name()
    width = max(len(n) for n in names)
    print(bold(f"  {'ACCOUNT'.ljust(width)}  EMAIL"))

    for name in names:
        try:
            summary = account_summary(load_account(name))
        except CliError as exc:
            summary = red(str(exc))
        marker = green("*") if name == current else " "
        label = bold(name) if name == current else name
        print(f"{marker} {pad(label, width)}  {summary}")

    if current is None:
        print()
        warn("the account logged in right now matches no saved account")
    return 0


def cmd_status(args):
    cfg = read_json(claude_config_path(), {}) or {}
    acct = cfg.get("oauthAccount") or {}
    if not acct:
        warn("not logged in")
        return 1

    name = find_by_uuid(acct.get("accountUuid"))
    label = bold(name) if name else yellow("(unsaved)")
    org = acct.get("organizationName")
    print(f"{green('[ok]')} current: {label}  "
          f"{acct.get('emailAddress', '?')}{dim(' @ ' + org) if org else ''}")

    blk = oauth_block(read_credentials())
    if blk.get("expiresAt"):
        left = (blk["expiresAt"] / 1000) - time.time()
        state = green("valid") if left > 0 else red("expired")
        remaining = dim(f", {int(left // 60)}m left") if left > 0 else ""
        plan = blk.get("subscriptionType")
        print(f"     token: {state}{remaining}"
              f"{dim('  plan: ' + plan) if plan else ''}")

    bound, source, origin = bindings.resolve()
    if bound:
        print(f"     here:  {bold(bound)}{_origin_note(source, origin)}"
              f"  {dim('via ' + shims.command_name() + ' run')}")
    return 0


def cmd_remove(args):
    path = account_path(args.name)
    if not os.path.exists(path):
        raise CliError(f"account '{args.name}' not found")
    if current_account_name() == args.name and not args.force:
        raise CliError(
            f"'{args.name}' is the account you are logged in as. "
            "Switch away first, or pass --force"
        )

    os.remove(path)
    legacy = os.path.join(store_dir(), args.name + "-dir")
    if os.path.isdir(legacy):
        shutil.rmtree(legacy, ignore_errors=True)
    if profiles.remove_profile(args.name):
        info(f"removed its profile {dim(profile_dir(args.name))}")
    dropped = bindings.forget_account(args.name)
    for directory in dropped:
        info(f"unbound {dim(directory)}")
    ok(f"removed {bold(args.name)}")
    return 0


def cmd_rename(args):
    old, new = args.name, args.new_name
    data = load_account(old)          # also rejects a v1 record
    if new == old:
        raise CliError(f"'{old}' is already called that")
    if slugify(new) != new:
        raise CliError(f"'{new}' cannot be a file name - "
                       f"try '{slugify(new)}'")
    if os.path.exists(account_path(new)):
        raise CliError(f"account '{new}' already exists - remove it first, "
                       "or pick another name")

    # Write the new record before dropping the old one: a duplicate can be
    # cleaned up by hand, a deleted account cannot.
    data["name"] = new
    save_account(data)
    os.remove(account_path(old))

    if profiles.rename_profile(old, new):
        info(f"moved its profile to {dim(profile_dir(new))}")
    for directory in bindings.rename_account(old, new):
        info(f"rebound {dim(directory)}")

    legacy = os.path.join(store_dir(), old + "-dir")
    if os.path.isdir(legacy):
        # Left alone it would be imported under the old name by `migrate`.
        try:
            os.rename(legacy, os.path.join(store_dir(), new + "-dir"))
        except OSError as exc:
            warn(f"could not rename the v1 snapshot dir: {exc}")

    ok(f"renamed {bold(old)} -> {bold(new)}  {account_summary(data)}")
    print(dim(f"     a .claude-account file naming {old} has to be edited "
              "by hand"))
    return 0


def cmd_usage(args):
    names = [args.name] if args.name else list_accounts()
    if not names:
        raise CliError("no accounts saved yet. Run: "
                       f"{shims.command_name()} save <name>")

    rows = []
    for name in names:
        try:
            data = load_account(name)
            rows.append((name, data, fetch_usage(token_for(data)), None))
        except CliError as exc:
            # ApiError already explains which call failed and why.
            rows.append((name, None, None, str(exc)))

    current = current_account_name()
    width = max(len(n) for n in names)
    print(bold(f"  {'ACCOUNT'.ljust(width)}  "
               f"{'SESSION (5h)'.ljust(23)}  WEEK (7d)"))

    for name, data, usage, error in rows:
        marker = green("*") if name == current else " "
        if error:
            print(f"{marker} {name.ljust(width)}  {red(error)}")
            continue
        five = usage.get("five_hour") or {}
        seven = usage.get("seven_day") or {}
        session = f"{fmt_pct(five)} {dim(fmt_reset(five.get('resets_at')))}"
        week = f"{fmt_pct(seven)} {dim(fmt_reset(seven.get('resets_at')))}"
        print(f"{marker} {name.ljust(width)}  {pad(session, 23)}  {week}")
        if args.verbose:
            print(dim(f"    {account_summary(data)}"))
    return 0


def cmd_migrate(args):
    return migrate.run()


def cmd_sync(args):
    info("sessions are shared automatically - switching only swaps "
         "credentials, and ~/.claude/projects is never touched.")

    # What is left for this command to do: an instance that died without
    # running its exit hook leaves refreshed tokens in its profile that the
    # store never saw. Folding them back keeps `usage` and `status` honest.
    names = profiles.list_profiles()
    if names:
        synced = [name for name in names if profiles.sync_back(name)]
        ok(f"reconciled {len(synced)}/{len(names)} profile(s) with the store"
           f"  {dim(', '.join(synced)) if synced else ''}")

    if migrate.has_legacy_dirs():
        warn(f"found v1 snapshot dir(s). Run `{shims.command_name()} "
             "migrate` to fold their sessions into the shared directory.")
    return 0


def cmd_update(args):
    return updater.run(check=args.check, do_rollback=args.rollback,
                       channel=args.channel, force=args.force)


def cmd_version(args):
    return updater.show_version()


def cmd_setup(args):
    return updater.setup(bootstrap=args.bootstrap, channel=args.channel)


def cmd_doctor(args):
    print(bold("install"))
    if updater.is_managed():
        manifest = updater.read_manifest()
        spare = updater.installed_versions()[1:]
        print(f"  kind:    managed  {dim(updater.install_root())}")
        print(f"  build:   {updater.read_pointer() or yellow('unset')}"
              f"  {dim('channel ' + manifest.get('channel', '?'))}")
        print(f"  shims:   {manifest.get('shim_dir') or yellow('unknown')}")
        print(f"  spare:   {', '.join(spare) or dim('none')}")
    else:
        print(f"  kind:    source checkout  {dim(updater.tree_root())}")
        print(dim("           update it with `git pull`"))

    print()
    print(bold("paths"))
    for label, path in (
        ("config", claude_config_path()),
        ("claude dir", claude_dir()),
        ("credentials", credentials_path()),
        ("store", store_dir()),
    ):
        state = green("found") if os.path.exists(path) else yellow("missing")
        print(f"  {label.ljust(12)} {path}  [{state}]")

    print()
    print(bold("credentials"))
    creds = read_credentials()
    if not creds:
        print(f"  {red('none')} - run `claude login`")
    else:
        blk = oauth_block(creds)
        source = "file" if os.path.exists(credentials_path()) else "keychain"
        print(f"  source: {source}")
        print(f"  scopes: {', '.join(blk.get('scopes') or []) or dim('none')}")
        print(f"  plan:   {blk.get('subscriptionType') or dim('unknown')}")

    print()
    print(bold("accounts"))
    names = list_accounts()
    print(f"  {len(names)} saved: {', '.join(names) or dim('none')}")
    print(f"  current: {current_account_name() or yellow('unsaved')}")

    print()
    print(bold("per-directory"))
    print(f"  profiles:  {profiles_dir()}")
    built = profiles.list_profiles()
    for name in built:
        shared, unshared = profiles.link_report(profile_dir(name))
        state = (green(f"{len(shared)} shared")
                 if not unshared
                 else yellow(f"{len(shared)} shared, "
                             f"{len(unshared)} not: {', '.join(unshared)}"))
        print(f"    {name.ljust(12)} {state}")
    if not built:
        print(dim("             none yet - "
                  f"`{shims.command_name()} bind <name>` makes one"))

    entries = bindings.read_bindings()
    print(f"  bindings:  {len(entries)} directory(ies)")
    bound, source, origin = bindings.resolve()
    print(f"  here:      {bold(bound) if bound else dim('unbound')}"
          f"{_origin_note(source, origin)}")

    print()
    print(bold("api"))
    token = oauth_block(read_credentials() or {}).get("accessToken")
    if not token:
        print(f"  usage  {yellow('skipped')} - no access token")
    else:
        try:
            fetch_usage(token)
            print(f"  usage  {green('reachable')}  {USAGE_URL}")
        except CliError as exc:
            print(f"  usage  {red('failed')}  {exc}")

    # Probe with a deliberately invalid grant: a 400 proves the endpoint is
    # there, which is what distinguishes "expired token" from "wrong URL".
    try:
        http_json(TOKEN_URL, stage="refresh", payload={
            "grant_type": "refresh_token",
            "refresh_token": "probe-invalid",
            "client_id": OAUTH_CLIENT_ID,
        })
        print(f"  token  {green('reachable')}  {TOKEN_URL}")
    except ApiError as exc:
        state = green("reachable") if exc.status == 400 else red("failed")
        note = "" if exc.status == 400 else f"  {exc}"
        print(f"  token  {state}  {TOKEN_URL}{note}")

    print()
    print(dim("  re-run any command with --debug to trace every request"))
    return 0
