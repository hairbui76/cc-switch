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

## Installation

### macOS / Linux (bash or zsh)

```bash
./init.sh
source ~/.bashrc     # or ~/.zshrc — init.sh tells you which
```

`init.sh` detects every rc file you have (`.bashrc`, `.zshrc`, and
`.bash_profile` on macOS) and installs into all of them. Re-running it is safe:
it replaces its own managed block instead of appending a second copy.

### Windows (PowerShell)

```powershell
.\init.ps1
. $PROFILE.CurrentUserAllHosts
```

If PowerShell blocks the script, allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Windows (Git Bash / WSL)

Use `./init.sh` — it works there too.

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
claude-switch doctor         # diagnose paths, credentials and API access
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
- Override paths with `CLAUDE_CONFIG_DIR` (Claude Code's own variable) and
  `CLAUDE_ACCOUNTS_DIR` (where this tool stores accounts).
- Pick a specific interpreter with `CLAUDE_SWITCH_PYTHON=/path/to/python`.

## Layout

```text
init.sh                     installer for bash + zsh
init.ps1                    installer for PowerShell
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
  migrate.py                  importing v1 backups
  paths.py                    where everything lives
  jsonio.py                   atomic JSON reads and writes
  term.py                     colours and status lines
```

The package can also be run directly:

```bash
PYTHONPATH=src python -m claude_accounts list
```
