#! /bin/bash

set -euo pipefail

me=$(realpath "${BASH_SOURCE[0]:-$0}")
readonly me
root=$(dirname "$me")/../..
readonly root

readonly plugin_data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/undo/udb_claude_code_plugin"
readonly uv_bin_dir="$plugin_data_dir/bin"

export PYTHONPATH="$root":${PYTHONPATH:-}
export UNDO_telemetry_ui=ai

# Return the path to the uv binary, checking PATH first, then local installation.
find_uv() {
    if command -v uv &>/dev/null; then
        command -v uv
    elif [[ -x "$uv_bin_dir/uv" ]]; then
        echo "$uv_bin_dir/uv"
    else
        return 1
    fi
}

# Download and install the uv binary to the plugin data directory.
install_uv() {
    echo "Downloading uv..." >&2
    if command -v curl &>/dev/null; then
        curl -fsSL https://astral.sh/uv/install.sh
    elif command -v wget &>/dev/null; then
        wget -qO- https://astral.sh/uv/install.sh
    else
        echo "Neither curl nor wget found. Please install one of them." >&2
        return 1
    fi | UV_INSTALL_DIR="$plugin_data_dir" sh >&2
}

if ! uv_path=$(find_uv); then
    install_uv
    if ! uv_path=$(find_uv); then
        echo "Failed to install uv" >&2
        exit 1
    fi
fi
export _UNDO_uv_path="$uv_path"  # Used bt `deps.py`.

exec "$uv_path" run --no-project --python 3.10 -m explain.claude_code_plugin "$@"
