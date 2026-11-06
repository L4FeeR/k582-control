#!/bin/sh
# Launcher: works from anywhere
DIR="$(dirname "$(readlink -f "$0")")"
exec env PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" python3 -m k582ctl "$@"
