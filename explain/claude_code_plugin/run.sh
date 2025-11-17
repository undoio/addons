#! /bin/bash

set -euo pipefail

readonly me=$(realpath "${BASH_SOURCE[0]:-$0}")
readonly root=$(dirname "$me")/../..

export PYTHONPATH
PYTHONPATH="$root":${PYTHONPATH:-}
readonly python=$(which python3 2> /dev/null)
if [[ -z "$python" ]]; then
    echo "python3 not found" >&2
    exit 1
fi

export UNDO_telemetry_ui=ai

# -S prevents site packages from being loaded.
exec "$python" -S -m explain.claude_code_plugin "$@"
