import os
from pathlib import Path


# IMPORTANT: only import standard library modules or modules with a similar warning here as this
# code must run before dependencies are installed.


def get_plugin_data_dir() -> Path:
    """
    Get the data directory (following the XDG specification) for the plugin's data.
    """
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        base_dir = Path(xdg_data_home)
    else:
        base_dir = Path.home() / ".local/share"

    plugin_dir = base_dir / "undo" / "udb_claude_code_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return plugin_dir
