#!/usr/bin/env sh
# Switch to the next account (round-robin).
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DIR/claude-switch.sh" next "$@"
