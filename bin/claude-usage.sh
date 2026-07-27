#!/usr/bin/env sh
# Show usage for every saved account.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DIR/claude-switch.sh" usage "$@"
