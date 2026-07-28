#!/usr/bin/env sh
# Point your shell at *this checkout* - for hacking on the tool itself.
# Commands run straight out of the working tree, so an edit takes effect with
# no reinstall, and updates come from `git pull`.
#
# For normal use install a managed copy instead, which can self-update:
#   curl -fsSL https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.sh | sh
#
# Supports bash and zsh, on Linux / macOS / Git Bash on Windows.

set -e

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BEGIN='# >>> cc-switch >>>'
END='# <<< cc-switch <<<'
# Markers from before the repo was renamed, stripped too so a re-run replaces
# an old block rather than leaving a second one behind.
OLD_BEGIN='# >>> claude-code-multi-account-switch >>>'
OLD_END='# <<< claude-code-multi-account-switch <<<'

# --- sanity check -----------------------------------------------------------
# Candidates must be *probed*, not just found on PATH: on Windows `python3` is
# usually the Microsoft Store stub, which exists but is not an interpreter.
PY=""
for py in "$CLAUDE_SWITCH_PYTHON" python3 python py; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' >/dev/null 2>&1 || continue
    PY="$py"
    break
done

if [ -z "$PY" ]; then
    echo "[xx] Python 3.7+ not found."
    echo "     Install it, or set CLAUDE_SWITCH_PYTHON=/path/to/python, then re-run."
    exit 1
fi
echo "[ok] $("$PY" --version 2>&1) at $(command -v "$PY")"

chmod +x "$DIR"/*.sh "$DIR"/bin/*.sh "$DIR/bin/claude-accounts.py" 2>/dev/null || true

SWITCH="$DIR/bin/claude-switch.sh"

# --- work out which rc files to touch ---------------------------------------
RC_FILES=""
add_rc() {
    case " $RC_FILES " in
        *" $1 "*) ;;
        *) RC_FILES="$RC_FILES $1" ;;
    esac
}

[ -f "$HOME/.bashrc" ] && add_rc "$HOME/.bashrc"
[ -f "$HOME/.zshrc" ] && add_rc "$HOME/.zshrc"
# macOS bash reads .bash_profile for login shells and often has no .bashrc.
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && [ -f "$HOME/.bash_profile" ]; then
    add_rc "$HOME/.bash_profile"
fi

# Nothing found - create the rc file matching the current shell.
if [ -z "$RC_FILES" ]; then
    case "${SHELL##*/}" in
        zsh) add_rc "$HOME/.zshrc" ;;
        *)   add_rc "$HOME/.bashrc" ;;
    esac
fi

# --- install ----------------------------------------------------------------
for rc in $RC_FILES; do
    tmp="$rc.claude-switch.tmp"
    if [ -f "$rc" ]; then
        # Strip our managed block (current and pre-rename), plus any v1
        # aliases, then re-append.
        sed -e "\|^$BEGIN\$|,\|^$END\$|d" \
            -e "\|^$OLD_BEGIN\$|,\|^$OLD_END\$|d" \
            -e '/^alias claude-switch=/d' \
            -e '/^alias claude-sync=/d' \
            -e '/^alias claude-next=/d' \
            -e '/^alias claude-usage=/d' \
            "$rc" > "$tmp"
    else
        : > "$tmp"
    fi

    cat >> "$tmp" <<EOF
$BEGIN
# Managed by init.sh (dev checkout at $DIR) - edit the repo, not this block.
alias cc="$SWITCH"
$END
EOF

    mv "$tmp" "$rc"
    echo "[ok] Installed into $rc"
done

echo ""
echo "Run this to activate now:"
for rc in $RC_FILES; do echo "  source $rc"; done
echo "  (or just open a new terminal)"
echo ""
echo "Commands:"
echo "  cc save <name>   Save the account you are logged in as"
echo "  cc <name>        Switch to an account"
echo "  cc list          List saved accounts"
echo "  cc status        Show the current account"
echo "  cc next          Switch to the next account"
echo "  cc usage         Usage for every account"
echo "  cc doctor        Diagnose setup problems"
echo ""
echo "This is a dev checkout: update it with \`git pull\`."
echo "\`cc update\` only works on a managed install."
echo ""
echo "Upgrading from v1? Run: cc migrate"
