#!/usr/bin/env sh
# Deprecated: sessions are shared between accounts automatically.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DIR/claude-switch.sh" sync "$@"
