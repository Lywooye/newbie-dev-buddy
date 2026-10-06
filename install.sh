#!/bin/sh
set -eu
buddy_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$buddy_root/scripts/install.py" "$@"
