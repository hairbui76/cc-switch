# Claude Code Multi-Account Switcher

Switch between multiple Claude Code accounts on **Windows, macOS and Linux** — with
sessions, settings and history shared across every account.

```text
$ claude-usage
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

No git required. The installer downloads a pinned build over HTTPS, puts real
`claude-switch` / `claude-next` / `claude-usage` executables on your `PATH`, and
records where they came from so the tool can update itself later.

They are **executables, not shell aliases**, so they also work from cron, from
scripts, and over `ssh host claude-usage`.

## Updating

```bash
claude-switch update             # fetch and install the newest build
claude-switch update --check     # only report whether one exists
claude-switch update --rollback  # go back to the build you had before
claude-switch version            # what is installed, from where
```

Nothing to pull, nothing to re-source: the launchers resolve the active build at
call time, so an update takes effect on the very next command.

### Channels

| Channel | Tracks | Use it when |
| --- | --- | --- |
| `main` (default) | every push to `main` | you want small fixes the moment they land |
| `stable` | the newest published GitHub release | you only want reviewed releases |

`stable` resolves through `/releases/latest`, which GitHub defines as the newest
non-draft, non-prerelease release — the tag listing endpoint is not guaranteed to
come back in chronological order.

```bash
claude-switch update --channel stable    # switch channel and update
```

The channel you pick is remembered, so later `claude-switch update` runs stay on
it.

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
~/.local/bin/claude-switch   launcher, reads `current` on every call
```

Updating writes a new directory and then rewrites one line in `current`. Nothing
is overwritten in place, so an interrupted update cannot leave a half-replaced
install behind, and a broken build is one pointer rewrite away from being undone.

On Windows the root is `%LOCALAPPDATA%\claude-switch` and the launchers go in
`%LOCALAPPDATA%\claude-switch\bin`, which the installer adds to your user `PATH`.

### If the commands go missing

```bash
claude-switch setup    # rebuild the launchers and the PATH entry
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
and updates come from `git pull`. `claude-switch update` deliberately refuses to
run here — it would have to overwrite your checkout — and tells you so.

`claude-switch version` and `claude-switch doctor` both report which mode you
are in.

If PowerShell blocks `init.ps1`, allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Usage

### Save an account

```bash
claude login                 # log in as usual
claude-switch save work      # store that login as "work"
claude-switch save           # or let it name the account from your email
```

### Switch

```bash
claude-switch work
claude-switch personal
claude-next                  # round-robin to the next account
```

The account you are leaving is auto-saved first, so rotated tokens are never
lost. If you were logged in as an account that had never been saved, it gets
stored under a name derived from your email rather than being thrown away.

### Inspect

```bash
claude-switch list           # all saved accounts, current one marked with *
claude-switch status         # current account + token expiry
claude-usage                 # usage for every account
claude-usage work            # ...or just one
```

`claude-usage` reads `GET /api/oauth/usage` with each account's stored token. It
does **not** switch accounts to collect the numbers, and it refreshes an expired
access token automatically.

### Manage

```bash
claude-switch remove old-account
claude-switch doctor         # diagnose install, paths, credentials, API access
claude-switch update         # install the newest build
```

## Troubleshooting

There is no log file. Add `--debug` to any command (or set
`CLAUDE_SWITCH_DEBUG=1`) to trace every HTTP request on stderr:

```bash
claude-usage --debug
```

```text
[db] work: token expired, refreshing
[db] POST https://api.anthropic.com/v1/oauth/token  (refresh)
[db]   -> 400 {"error": "invalid_grant", ...}
```

`claude-switch doctor` checks both endpoints the tool depends on, so a broken
URL is distinguishable from a broken token.

| `claude-usage` says | Meaning |
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
claude-switch migrate
```

This reads the credentials out of each `~/.claude-accounts/<name>-dir/`
snapshot, rewrites it in the new format, and copies any session files that exist
*only* inside a snapshot into your shared `~/.claude/projects/` (existing files
are never overwritten). Once you have confirmed every account works, the old
`*-dir` folders can be deleted.

`claude-sync` still exists but is now a no-op that tells you sessions are
already shared.

## Notes

- Accounts live in `~/.claude-accounts/<name>.json`, written with `0600`
  permissions. **They contain OAuth tokens — do not commit or share them.**
- `~/.claude.json` is backed up to `~/.claude-accounts/.claude.json.bak` before
  every switch.
- Quit Claude Code before switching. A running instance rewrites `~/.claude.json`
  when it exits and would restore the previous account's identity.
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
  claude-next.sh              shortcuts for `claude-switch <subcommand>`
  claude-usage.sh
  claude-sync.sh
src/claude_accounts/        all logic, stdlib only
  cli.py                      argument parsing, entry point
  commands.py                 one function per subcommand
  store.py                    save / load / apply accounts
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
makes `claude-switch update` fail with a message and leave the working build in
place; it cannot brick an install.

The package can also be run directly:

```bash
PYTHONPATH=src python -m claude_accounts list
```
