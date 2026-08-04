"""Per-directory accounts: several Claude Code windows, different logins.

`cc use` swaps the one live login, so every window on the machine follows it.
A profile applies the same idea to a single process instead of the whole
machine: a second config directory holding *only* the two files that say who is
logged in - `.credentials.json` and `.claude.json` - with everything else in
~/.claude linked back to the originals. Pointing `CLAUDE_CONFIG_DIR` at it
gives one Claude Code process its own identity while it still reads and writes
the same sessions, settings, history and skills as every other window.

Profiles are keyed by account rather than by directory, so two repositories
bound to the same account share one profile - and therefore one set of tokens,
which is exactly what two windows on the same login do today.
"""

import os
import shutil
import signal
import subprocess
import sys

from .credentials import oauth_block
from .jsonio import read_json, write_json
from .paths import (claude_config_path, claude_dir, profile_dir, profiles_dir)
from .store import (ACCOUNT_CONFIG_KEYS, build_account, save_account)
from .term import CliError, warn

# Everything in ~/.claude is linked into a profile except these: the files that
# say who is logged in, the caches the server fills in per account, and the
# lock that guards a token refresh. Anything Claude Code adds in a future
# release is therefore shared by default, which is the promise the rest of the
# tool makes.
PRIVATE_ENTRIES = frozenset((
    ".credentials.json",
    ".claude.json",
    ".claude.json.backup",
    ".oauth_refresh.lock",
    ".last-cleanup",
    ".last-update-result.json",
    "policy-limits.json",
    "remote-settings.json",
    "mcp-needs-auth-cache.json",
    "backups",
    "statsig",
    "telemetry",
    "debug",
))


# --------------------------------------------------------------------------
# links
# --------------------------------------------------------------------------

def _is_link(path: str) -> bool:
    """True for a symlink or a Windows directory junction."""
    if os.path.islink(path):
        return True
    try:
        # Junctions are not symlinks and islink() says so, but readlink() has
        # answered for them since 3.8.
        os.readlink(path)
        return True
    except (OSError, ValueError, NotImplementedError):
        return False


def _same(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        pass
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def _drop_link(path: str) -> None:
    """Remove a link without touching whatever it points at."""
    try:
        os.unlink(path)
    except OSError:
        # A directory symlink or junction on Windows refuses unlink; rmdir
        # removes the link itself and leaves the target alone.
        os.rmdir(path)


def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return -1.0


def _make_link(src: str, dst: str, is_dir: bool):
    """Link dst -> src by whatever means this platform allows.

    Returns the mechanism used, or None if none of them worked.
    """
    try:
        os.symlink(src, dst, target_is_directory=is_dir)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass

    if os.name != "nt":
        return None

    if is_dir:
        # Symlinks on Windows need Developer Mode or an elevated shell;
        # junctions need no privilege at all.
        try:
            out = subprocess.run(["cmd", "/c", "mklink", "/J", dst, src],
                                 capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError):
            return None
        return "junction" if out.returncode == 0 else None

    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        return None


def _link_dir(src: str, dst: str, label: str) -> None:
    if os.path.lexists(dst):
        if _same(src, dst):
            return
        if not _is_link(dst):
            warn(f"{label}: the profile has a real directory here, "
                 "leaving it unshared")
            return
        _drop_link(dst)

    if _make_link(src, dst, True) is None:
        warn(f"could not link {label} into the profile - "
             "that directory will not be shared")


def _link_file(src: str, dst: str, label: str) -> None:
    if os.path.lexists(dst):
        if _same(src, dst):
            return
        # A hardlink survives appends but not the write-temp-then-rename that
        # Claude Code uses, so the two copies drift apart the first time the
        # file is rewritten. Keep whichever was written last and link again,
        # which turns every launch and every exit into a repair.
        if _mtime(dst) > _mtime(src):
            try:
                shutil.copy2(dst, src)
            except OSError as exc:
                warn(f"{label}: could not fold the profile's copy back "
                     f"into {src}: {exc}")
                return
        try:
            _drop_link(dst) if _is_link(dst) else os.remove(dst)
        except OSError as exc:
            warn(f"{label}: could not replace the profile's copy: {exc}")
            return

    if _make_link(src, dst, False) is None:
        try:
            shutil.copy2(src, dst)
        except OSError as exc:
            warn(f"could not share {label}: {exc}")
            return
        warn(f"{label}: copied instead of linked - "
             "edits inside this profile stay in the profile")


def link_shared(profile: str) -> None:
    """(Re)point everything shareable in `profile` at ~/.claude.

    Run on every launch and again on exit, so an entry Claude Code replaced
    with a file of its own is repaired rather than quietly forked.
    """
    root = claude_dir()
    try:
        entries = sorted(os.listdir(root))
    except OSError as exc:
        raise CliError(f"cannot read {root}: {exc}")

    for entry in entries:
        if entry in PRIVATE_ENTRIES:
            continue
        src = os.path.join(root, entry)
        dst = os.path.join(profile, entry)
        if os.path.isdir(src):
            _link_dir(src, dst, entry)
        elif os.path.isfile(src):
            _link_file(src, dst, entry)


def link_report(profile: str):
    """(shared, unshared) entry names, for `cc doctor`."""
    shared, unshared = [], []
    root = claude_dir()
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return shared, unshared

    for entry in entries:
        if entry in PRIVATE_ENTRIES:
            continue
        src = os.path.join(root, entry)
        dst = os.path.join(profile, entry)
        if not os.path.lexists(dst):
            continue
        (shared if _same(src, dst) else unshared).append(entry)
    return shared, unshared


# --------------------------------------------------------------------------
# the profile itself
# --------------------------------------------------------------------------

def list_profiles():
    root = profiles_dir()
    if not os.path.isdir(root):
        return []
    return sorted(entry for entry in os.listdir(root)
                  if os.path.isdir(os.path.join(root, entry)))


def credentials_path_for(name: str) -> str:
    return os.path.join(profile_dir(name), ".credentials.json")


def config_path_for(name: str) -> str:
    return os.path.join(profile_dir(name), ".claude.json")


def profile_credentials(name):
    """Credentials as last written *inside* a profile, or None.

    An account only ever launched through `cc run` refreshes its tokens in
    there, so this copy can be newer than the store's.
    """
    if not name:
        return None
    return read_json(credentials_path_for(name))


def _expiry(creds) -> float:
    value = oauth_block(creds).get("expiresAt")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _write_config(name: str, data) -> None:
    """The profile's own ~/.claude.json: shared state, this account's identity.

    Seeded from the live config the first time so the profile inherits
    onboarding, trusted directories and project history instead of dropping the
    user into the first-run wizard. After that it is the profile's own file and
    only the identity keys are kept in step with the store.
    """
    target = config_path_for(name)
    cfg = read_json(target)
    if cfg is None:
        cfg = read_json(claude_config_path(), {}) or {}

    saved = data.get("config") or {}
    for key in ACCOUNT_CONFIG_KEYS:
        if key in saved:
            cfg[key] = saved[key]
        else:
            # Never leave another account's value behind.
            cfg.pop(key, None)
    write_json(target, cfg, private=True)


def _write_credentials(name: str, data) -> None:
    """Install the stored tokens, unless the profile's are newer.

    An instance killed without running its exit hook (a crash, a closed
    terminal) leaves tokens in the profile that the store never saw. Refresh
    tokens rotate, so overwriting them with the store's older copy would hand
    Claude Code a token the server has already retired.
    """
    target = credentials_path_for(name)
    live = read_json(target)
    stored = data.get("credentials")

    if live and _expiry(live) > _expiry(stored):
        data["credentials"] = live
        save_account(build_account(name, live,
                                   read_json(config_path_for(name), {}) or {}))
        return

    if not stored:
        # Nothing to install - whatever the profile has is all there is.
        return
    write_json(target, stored, private=True)


def ensure_profile(data) -> str:
    """Create or refresh the config directory for account `data`."""
    name = data["name"]
    path = profile_dir(name)
    os.makedirs(path, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

    link_shared(path)
    _write_config(name, data)
    _write_credentials(name, data)
    return path


def sync_back(name: str) -> bool:
    """Fold what an instance wrote in its profile back into the store.

    Tokens rotate while Claude Code runs, so without this the store would go
    stale for any account only ever used through `cc run` - and `cc usage`
    would be reporting on a refresh token that no longer works.
    """
    creds = read_json(credentials_path_for(name))
    blk = oauth_block(creds)
    if not (blk.get("accessToken") or blk.get("refreshToken")):
        # Claude Code blanks this file when a login expires past repair. Saving
        # that over the store would destroy the refresh token `cc usage` and a
        # later `claude login` can still be recovered from, so keep ours.
        if creds is not None:
            warn(f"{name}: no tokens left in the profile - kept the stored "
                 "copy; run `claude login` in that window to sign in again")
        link_shared(profile_dir(name))
        return False

    cfg = read_json(config_path_for(name), {}) or {}
    save_account(build_account(name, creds, cfg))
    link_shared(profile_dir(name))
    return True


def rename_profile(old: str, new: str) -> bool:
    """Move a profile to a new account name.

    The links inside it are absolute, so moving the directory leaves them
    pointing exactly where they did.
    """
    source = profile_dir(old)
    if not os.path.isdir(source):
        return False

    target = profile_dir(new)
    if os.path.isdir(target):
        # An orphan from an earlier rename or removal. Unlink it properly
        # rather than let os.rename fail on a directory that is not empty.
        remove_profile(new)

    try:
        os.rename(source, target)
    except OSError as exc:
        warn(f"could not move the profile to {target}: {exc}")
        return False
    return True


def remove_profile(name: str) -> bool:
    """Delete a profile. Only the links are lost; ~/.claude is untouched."""
    path = profile_dir(name)
    if not os.path.isdir(path):
        return False
    # Every shared entry is a link, so a plain rmtree could walk into
    # ~/.claude and delete the real sessions. Unlink the links first.
    for entry in sorted(os.listdir(path)):
        target = os.path.join(path, entry)
        if _is_link(target):
            try:
                _drop_link(target)
            except OSError as exc:
                warn(f"could not unlink {target}: {exc}")
                return False
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.isdir(path)


# --------------------------------------------------------------------------
# launching
# --------------------------------------------------------------------------

def claude_executable() -> str:
    name = os.environ.get("CLAUDE_SWITCH_CLAUDE") or "claude"
    found = shutil.which(name)
    if not found:
        raise CliError(
            f"cannot find `{name}` on PATH - install Claude Code, or point "
            "CLAUDE_SWITCH_CLAUDE at its executable"
        )
    return found


def _swallow_interrupt() -> None:
    """Stop Ctrl-C from killing this wrapper: the key belongs to Claude Code.

    A no-op handler rather than SIG_IGN, because SIG_IGN is inherited through
    exec and would leave Claude Code itself deaf to Ctrl-C.
    """
    def ignore(signum, frame):
        pass

    try:
        signal.signal(signal.SIGINT, ignore)
    except (ValueError, OSError, AttributeError):
        pass


def launch(data, argv) -> int:
    """Run Claude Code against `data`'s profile and wait for it to exit."""
    path = ensure_profile(data)
    executable = claude_executable()

    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = path
    env["CLAUDE_SWITCH_ACCOUNT"] = data["name"]

    _swallow_interrupt()
    # Say which account this is *before* Claude Code takes over the terminal;
    # a redirected stdout is block-buffered and would otherwise print it last.
    sys.stdout.flush()
    try:
        proc = subprocess.Popen([executable] + list(argv), env=env)
    except OSError as exc:
        raise CliError(f"could not start {executable}: {exc}")

    while True:
        try:
            code = proc.wait()
            break
        except KeyboardInterrupt:
            # Windows raises this in the parent as well; the child is handling
            # the key, so keep waiting for it.
            continue

    sync_back(data["name"])
    return code


def env_exports(data, shell: str):
    """Lines that put a shell (or an IDE, or direnv) on this account.

    The escape hatch for anything that launches `claude` itself instead of
    going through `cc run`: VS Code's integrated terminal, a wrapper script, a
    long-lived tmux pane.

    `plain` emits bare `KEY=VALUE` for consumers that read the pairs
    themselves rather than eval'ing a shell: agent-of-empires'
    `host_hooks.before_session`, `docker --env-file`, systemd
    `EnvironmentFile`. No quoting is applied, because nothing downstream
    unquotes it -- a quote would land in the value.
    """
    path = ensure_profile(data)
    if shell == "posix" and os.name == "nt":
        # A backslash is an escape in most POSIX shells; Node reads either
        # separator, so hand the forward-slash form to bash and zsh.
        path = path.replace("\\", "/")
    pairs = (("CLAUDE_CONFIG_DIR", path),
             ("CLAUDE_SWITCH_ACCOUNT", data["name"]))

    if shell == "powershell":
        return [f'$env:{key} = "{value}"' for key, value in pairs]
    if shell == "cmd":
        return [f'set "{key}={value}"' for key, value in pairs]
    if shell == "plain":
        return [f"{key}={value}" for key, value in pairs]
    return [f'export {key}="{value}"' for key, value in pairs]
