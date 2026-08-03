# Claude Code Multi-Account Switcher

Switch between multiple Claude Code accounts on **Windows, macOS and Linux** — with
sessions, settings and history shared across every account.

```text
$ cc usage
  ACCOUNT   SESSION (5h)             WEEK (7d)
* work       21% Tue 00:50 (3h33m)    20% Mon 06:00 (6d8h)
  personal    4% Tue 02:15 (4h58m)     9% Mon 06:00 (6d8h)
```

## How it works

Only your **credentials** are per-account. Switching swaps:

- `~/.claude/.credentials.json` (the macOS Keychain entry, if that's where your
  tokens live)
- a handful of identity keys inside `~/.claude.json` — `oauthAccount`, `userID`,
  and the account-scoped caches

Everything else stays exactly where it is and is therefore **shared by every
account automatically**:

```text
~/.claude/projects/      <- your sessions (claude --resume works on any account)
~/.claude/sessions/
~/.claude/history.jsonl
~/.claude/settings.json
~/.claude/todos/  plugins/  skills/  ...
~/.claude.json -> projects, mcpServers, and everything not listed above
```

There is nothing to sync. `claude --resume` sees the same sessions no matter
which account you are on.

Switching is machine-wide: every window follows the account you switch to. To
run **one account per directory, several windows at once**, bind the directory
and start Claude Code with `cc run` — see [Two accounts at the same
time](#two-accounts-at-the-same-time-one-per-directory).

## Requirements

- Python 3.7+ (standard library only — nothing to `pip install`)
- Claude Code
- `curl` (or `wget`) and `tar` to run the installer — git is *not* required

## Installation

### macOS / Linux / Git Bash / WSL

```bash
curl -fsSL https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.sh | sh
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.ps1 | iex
```

Then open a new terminal, or `source ~/.bashrc` — the installer tells you which.

No git required. The installer downloads a pinned build over HTTPS, puts a
real `cc` executable on your `PATH`, and records where it came from so the tool
can update itself later.

It is an **executable, not a shell alias**, so it also works from cron, from
scripts, and over `ssh host cc usage`.

### A note on the name `cc`

On Unix, `cc` is traditionally the C compiler (`/usr/bin/cc`, usually a symlink
to gcc or clang), and the installer puts its own directory **first** on `PATH`.
On a machine that compiles anything, `cc` will therefore resolve to this tool
and any `Makefile` defaulting to `CC=cc` will break.

The installer checks for this and warns if it finds another `cc`. To install
under a different name:

```bash
CLAUDE_SWITCH_NAME=ccs curl -fsSL https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.sh | sh
```

Every message the tool prints then refers to `ccs`, because the launcher tells
the CLI which name it was invoked under. Re-running `ccs setup` keeps that name;
switching names retires the old launcher rather than leaving two behind.

## Updating

```bash
cc update             # fetch and install the newest build
cc update --check     # only report whether one exists
cc update --rollback  # go back to the build you had before
cc version            # what is installed, from where
```

Nothing to pull, nothing to re-source: the launcher resolves the active build
at call time, so an update takes effect on the very next command.

### Channels

| Channel | Tracks | Use it when |
| --- | --- | --- |
| `main` (default) | every push to `main` | you want small fixes the moment they land |
| `stable` | the newest published GitHub release | you only want reviewed releases |

`stable` resolves through `/releases/latest`, which GitHub defines as the newest
non-draft, non-prerelease release — the tag listing endpoint is not guaranteed to
come back in chronological order.

```bash
cc update --channel stable    # switch channel and update
```

The channel you pick is remembered, so later `cc update` runs stay on it.

A build is identified as `<version>-<short sha>`, e.g. `2.1.0-a1b2c3d`. The sha
is what makes two pushes that share a version number distinguishable, so a fix
pushed without a version bump is still detected as an update.

### What an install looks like on disk

```text
~/.claude-switch/
  versions/2.1.0-a1b2c3d/    the build in use
  versions/2.0.0-9f8e7d6/    kept so --rollback has somewhere to go
  current                    one line: the active build's directory name
  manifest.json              repo, channel, sha, previous build
~/.local/bin/cc              launcher, reads `current` on every call
```

Updating writes a new directory and then rewrites one line in `current`. Nothing
is overwritten in place, so an interrupted update cannot leave a half-replaced
install behind, and a broken build is one pointer rewrite away from being undone.

On Windows the root is `%LOCALAPPDATA%\claude-switch` and the launcher goes in
`%LOCALAPPDATA%\claude-switch\bin`, which the installer adds to your user `PATH`.
A `cc.cmd` is written alongside the extensionless `cc`, so cmd.exe, PowerShell
and Git Bash all find a working launcher.

### Coming from `claude-switch`

Releases up to 2.2.1 installed three commands: `claude-switch`, `claude-next`
and `claude-usage`. They are now one `cc`, with the old two as subcommands.

`cc update` alone will **not** rename anything: an update is carried out by the
copy already installed, so it writes the launchers that version knows about.
Re-run the installer once instead — it runs the new code, which writes `cc` and
removes the launchers it previously generated:

```bash
curl -fsSL https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.sh | sh
```

| Before | Now |
| --- | --- |
| `claude-switch save work` | `cc save work` |
| `claude-switch work` | `cc work` |
| `claude-next` | `cc next` |
| `claude-usage` | `cc usage` |

Saved accounts are untouched by any of this.

### If the command goes missing

```bash
cc setup    # rebuild the launcher and the PATH entry
```

Re-running the `curl` installer also works and is equivalent to a fresh install.

## Working on the tool itself

For a git checkout you can edit in place:

```bash
git clone https://github.com/hairbui76/cc-switch
cd cc-switch
./init.sh          # or .\init.ps1 on PowerShell
```

This points your shell at the working tree, so an edit takes effect immediately
and updates come from `git pull`. `cc update` deliberately refuses to
run here — it would have to overwrite your checkout — and tells you so.

`cc version` and `cc doctor` both report which mode you
are in.

If PowerShell blocks `init.ps1`, allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Usage

### Save an account

```bash
claude login                 # log in as usual
cc save work      # store that login as "work"
cc save           # or let it name the account from your email
```

### Switch

```bash
cc work
cc personal
cc next                      # round-robin to the next account
```

The account you are leaving is auto-saved first, so rotated tokens are never
lost. If you were logged in as an account that had never been saved, it gets
stored under a name derived from your email rather than being thrown away.

### Inspect

```bash
cc list           # all saved accounts, current one marked with *
cc status         # current account + token expiry
cc usage                     # usage for every account
cc usage work            # ...or just one
```

`cc usage` reads `GET /api/oauth/usage` with each account's stored token. It
does **not** switch accounts to collect the numbers, and it refreshes an expired
access token automatically.

### Manage

```bash
cc remove old-account
cc doctor         # diagnose install, paths, credentials, API access
cc update         # install the newest build
```

## Two accounts at the same time, one per directory

`cc use` swaps the *one* live login, so every Claude Code window on the machine
follows it. Bind a directory instead and that directory gets its own account —
and those windows run side by side:

```bash
cd ~/work/api     && cc bind work
cd ~/side/scraper && cc bind personal

cd ~/work/api     && cc run     # this window is work
cd ~/side/scraper && cc run     # this one is personal, at the same time
```

`cc bind` with no name binds the account you are logged in as right now.
Everything after `cc run` goes straight to Claude Code, so `cc run --resume`,
`cc run --model opus` and `cc run mcp list` all work as usual.

```bash
cc bindings           # every directory -> account, with the one you are in marked
cc unbind             # drop this directory's binding (the account is kept)
cc status             # ... now also says which account this directory runs as
```

### How it works

`cc run` starts Claude Code with `CLAUDE_CONFIG_DIR` pointed at a per-account
**profile** — a second config directory holding *only* the two files that say
who is logged in. Everything else is a link back to `~/.claude`, so the sharing
guarantee is the same one the rest of this tool makes:

```text
~/.claude-accounts/profiles/work/
  .credentials.json     this account's tokens        <- per account
  .claude.json          identity + this profile's own state
  projects -> ~/.claude/projects        sessions     <- shared, one copy on disk
  settings.json -> ~/.claude/settings.json
  skills/ plugins/ history.jsonl plans/ ...
```

Everything Claude Code puts in `~/.claude` is shared unless it names an
account: `.credentials.json`, `.claude.json`, and the caches the server fills
in per login (`policy-limits.json`, `remote-settings.json`, `statsig`,
`backups`, `telemetry`, `debug`). Anything a future release adds is shared by
default. `cc doctor` lists what ended up shared per profile.

Profiles are keyed by account, not by directory, so ten repositories bound to
`work` share one profile and one set of tokens — exactly what ten windows on one
login do today.

Tokens rotate while Claude Code runs, so `cc run` folds the profile's
credentials back into the saved account when the window exits. That keeps
`cc usage` and `cc status` reporting on tokens that still work. If a window is
killed before it gets there, `cc sync` reconciles every profile.

### Directory to account

Resolved in this order, nearest first:

| Source | Wins over | Use it for |
| --- | --- | --- |
| `CLAUDE_SWITCH_ACCOUNT` | everything | one-off overrides; `cc run` sets it for the window it starts, so a shell inside that window stays on the same account |
| `.claude-account` in the directory | bindings | a repository that should carry the decision with it (one line: the account name) |
| `cc bind` | — | the normal case; kept in `~/.claude-accounts/.bindings.json`, so nothing is added to your repositories |

A directory inherits the binding of its nearest bound parent, so
`cc bind work --path ~/work` covers every checkout under `~/work`. `cc run -a
personal` ignores all of it for one command.

### Anything that starts `claude` itself

VS Code, a wrapper script, direnv, a long-lived tmux pane — `cc env` prints the
two variables that put a whole shell on this directory's account:

```bash
eval "$(cc env)"        # then plain `claude` in this shell is that account
cc env --format powershell
```

For a VS Code workspace, put the same value in
`.vscode/settings.json` → `terminal.integrated.env.<platform>`:

```json
{
  "terminal.integrated.env.windows": {
    "CLAUDE_CONFIG_DIR": "C:\\Users\\you\\.claude-accounts\\profiles\\work"
  }
}
```

Only `cc run` syncs tokens back on exit, so run `cc sync` now and then if you
launch Claude Code this way.

### What is not shared

- **`.claude.json` is per profile.** It is seeded from your live one the first
  time — onboarding, trusted directories and project history come along — but
  after that each account keeps its own. User-scope MCP servers added with
  `claude mcp add` therefore have to be added per account; a project-scope
  `.mcp.json` in the repository is shared by everyone.
- **Windows has no unprivileged file symlinks**, so `settings.json` and
  `history.jsonl` are hardlinked and directories become junctions. Claude Code
  rewrites a file by renaming a new one over it, which breaks a hardlink — so
  `cc run` re-links on launch and on exit, keeping whichever copy was written
  last. Two windows editing settings at the same time is last-one-out-wins.
- **macOS Keychain.** A profile keeps its tokens in
  `<profile>/.credentials.json`, which is the copy Claude Code prefers when it
  is there. If a bound window comes up as the wrong account, that is the thing
  to report.

`cc remove <name>` deletes the account, its profile and every binding pointing
at it. Only links are removed — `~/.claude` is never touched.

## Troubleshooting

There is no log file. Add `--debug` to any command (or set
`CLAUDE_SWITCH_DEBUG=1`) to trace every HTTP request on stderr:

```bash
cc usage --debug
```

```text
[db] work: token expired, refreshing
[db] POST https://api.anthropic.com/v1/oauth/token  (refresh)
[db]   -> 400 {"error": "invalid_grant", ...}
```

`cc doctor` checks both endpoints the tool depends on, so a broken
URL is distinguishable from a broken token.

| `cc usage` says | Meaning |
| --- | --- |
| `refresh token rejected` | The stored refresh token is dead. Switch to that account and run `claude login`. |
| `token rejected` | The access token was refused and could not be refreshed. Log in again. |
| `rate limited` | Too many requests. Wait and retry. |
| `usage: HTTP 404` | The API moved. Check `doctor`, then open an issue. |
| `-%` in a column | The API returned no number for that window, which is normal for some plans. |

## Upgrading from v1

v1 stored a full copy of `~/.claude` per account, which is what caused sessions
to be rolled back on every switch. To import those backups:

```bash
cc migrate
```

This reads the credentials out of each `~/.claude-accounts/<name>-dir/`
snapshot, rewrites it in the new format, and copies any session files that exist
*only* inside a snapshot into your shared `~/.claude/projects/` (existing files
are never overwritten). Once you have confirmed every account works, the old
`*-dir` folders can be deleted.

`cc sync` no longer copies sessions around — they are already shared. What it
does now is reconcile the per-directory profiles described above with the saved
accounts, which matters only if a bound window was killed before it could.

## Notes

- Accounts live in `~/.claude-accounts/<name>.json`, written with `0600`
  permissions. **They contain OAuth tokens — do not commit or share them.**
- Profiles live in `~/.claude-accounts/profiles/<name>/` and bindings in
  `~/.claude-accounts/.bindings.json`. A profile is rebuilt from the saved
  account whenever it is used, so deleting one costs nothing.
- `~/.claude.json` is backed up to `~/.claude-accounts/.claude.json.bak` before
  every switch.
- Quit Claude Code before switching. A running instance rewrites `~/.claude.json`
  when it exits and would restore the previous account's identity. A window
  started with `cc run` writes to its own profile instead, so it neither
  clobbers a switch nor is clobbered by one.
- On macOS, credentials are read from and written to the Keychain
  (`Claude Code-credentials`) when no `.credentials.json` file exists.
- Accounts and the install are independent. Reinstalling, updating or rolling
  back never touches `~/.claude-accounts/`.

### Environment variables

| Variable | Effect |
| --- | --- |
| `CLAUDE_CONFIG_DIR` | Claude Code's own data directory |
| `CLAUDE_ACCOUNTS_DIR` | where saved accounts are stored |
| `CLAUDE_SWITCH_PYTHON` | interpreter to use |
| `CLAUDE_SWITCH_HOME` | install root (default `~/.claude-switch`) |
| `CLAUDE_SWITCH_NAME` | what to call the command (default `cc`) |
| `CLAUDE_SWITCH_ACCOUNT` | account `cc run` should use, ahead of any binding |
| `CLAUDE_SWITCH_CLAUDE` | the `claude` executable `cc run` should start |
| `CLAUDE_SWITCH_BIN` | directory the launchers go into |
| `CLAUDE_SWITCH_CHANNEL` | channel for a fresh install: `main` or `stable` |
| `CLAUDE_SWITCH_REPO` | `owner/name` to install and update from, e.g. a fork |
| `GITHUB_TOKEN` | raises the GitHub API rate limit for update checks |
| `CLAUDE_SWITCH_DEBUG` | trace every HTTP request |

## Layout

```text
VERSION                     the published version, read by the updater
release-please-config.json  release automation: bumps VERSION, tags, releases
.release-please-manifest.json   the version release-please believes is current
.github/workflows/          release-please
install.sh                  curl installer: managed, self-updating copy
install.ps1                 the same for PowerShell
init.sh                     dev installer: point a shell at this checkout
init.ps1                    the same for PowerShell
bin/                        entry points only - no logic
  claude-switch.sh   .ps1     find a usable Python, hand off to the launcher
  claude-accounts.py          launcher: puts src/ on sys.path, calls the CLI
src/claude_accounts/        all logic, stdlib only
  cli.py                      argument parsing, entry point
  commands.py                 one function per subcommand
  store.py                    save / load / apply accounts
  profiles.py                 per-account config dirs for `cc run`
  bindings.py                 which directory runs under which account
  credentials.py              .credentials.json and the macOS Keychain
  api.py                      OAuth usage + token refresh
  updater.py                  version resolution, download, activate, rollback
  shims.py                    the claude-* launchers and PATH wiring
  migrate.py                  importing v1 backups
  paths.py                    where everything lives
  jsonio.py                   atomic file reads and writes
  term.py                     colours and status lines
```

## Releasing

Versioning is automated by
[release-please](https://github.com/googleapis/release-please). You never edit
`VERSION` or tag by hand.

Write [Conventional Commits](https://www.conventionalcommits.org/) on `main`:

| Commit prefix | Effect on the next release |
| --- | --- |
| `fix: ...` | patch bump — `2.1.0` → `2.1.1` |
| `feat: ...` | minor bump — `2.1.0` → `2.2.0` |
| `feat!: ...` or a `BREAKING CHANGE:` footer | major bump — `2.1.0` → `3.0.0` |
| `docs:`, `refactor:`, `perf:`, `build:` | listed in the changelog, no bump on their own |
| `chore:`, `ci:`, `test:`, `style:` | no bump, hidden from the changelog |

On every push to `main`, the workflow opens or updates a single **release PR**
that bumps `VERSION` and writes `CHANGELOG.md`. Merging that PR tags the commit
`vX.Y.Z` and publishes a GitHub release.

```text
push `fix:` to main  ->  release PR "chore(main): release 2.1.1"  ->  merge
                                                                       |
                    `main` channel users already had the fix           |
                    `stable` channel users get it here  <--------------+
```

Config lives in [`release-please-config.json`](release-please-config.json) and
current versions in
[`.release-please-manifest.json`](.release-please-manifest.json). The `simple`
release type is used with `version-file` pointed at `VERSION`, so the file the
updater reads over a raw URL stays the single source of truth.

### One-time repo setup

The workflow needs the repository to let Actions open pull requests:

> Settings → Actions → General → Workflow permissions →
> **Allow GitHub Actions to create and approve pull requests**

Without it the job fails with `GitHub Actions is not permitted to create or
approve pull requests`. The `permissions:` block in the workflow raises what
`GITHUB_TOKEN` is allowed to do, but that checkbox is a repo-level veto on top
of it and cannot be granted from the workflow file.

After granting it, start a run from **Actions → release-please → Run workflow**
rather than pushing a throwaway commit.

The alternative, if you would rather not enable it, is a fine-grained PAT with
`contents: write` and `pull-requests: write`, stored as a repository secret and
referenced instead of `secrets.GITHUB_TOKEN`.

A commit that is not a Conventional Commit is simply not counted toward the next
version. It still reaches `main` channel users immediately — the short sha in the
build name is what marks it as a new build, so a fix does not need a version bump
to be picked up.

### Why a broken push is not a broken install

Clients verify a download by running its `--version` before activating it, and
only then rewrite the `current` pointer. A push that fails to import therefore
makes `cc update` fail with a message and leave the working build in
place; it cannot brick an install.

The package can also be run directly:

```bash
PYTHONPATH=src python -m claude_accounts list
```
