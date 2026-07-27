"""One function per subcommand. All of them return a process exit code."""

import os
import shutil
import time

from . import migrate, updater
from .api import (OAUTH_CLIENT_ID, TOKEN_URL, USAGE_URL, ApiError, fetch_usage,
                  fmt_pct, fmt_reset, http_json, token_for)
from .credentials import oauth_block, read_credentials
from .jsonio import read_json
from .paths import (account_path, claude_config_path, claude_dir,
                    credentials_path, store_dir)
from .store import (account_summary, current_account_name,
                    current_account_uuid, find_by_uuid, list_accounts,
                    load_account, apply_account, slugify, snapshot_current,
                    unique_name)
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
        raise CliError("no accounts saved yet. Run: claude-switch save <name>")
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


def cmd_list(args):
    names = list_accounts()
    if not names:
        warn("no accounts saved yet. Run: claude-switch save <name>")
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
    ok(f"removed {bold(args.name)}")
    return 0


def cmd_usage(args):
    names = [args.name] if args.name else list_accounts()
    if not names:
        raise CliError("no accounts saved yet. Run: claude-switch save <name>")

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
    info("sessions are shared automatically now - "
         "`claude-sync` is no longer needed.")
    info("Switching only swaps credentials; "
         "~/.claude/projects is never touched.")
    if migrate.has_legacy_dirs():
        warn("found v1 snapshot dir(s). Run `claude-switch migrate` to fold "
             "their sessions into the shared directory.")
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
