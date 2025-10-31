# IMPORTANT: only import standard library modules available in any Python 3 version here.
#
# This module is run as part of the initialisation process before dependencies are installed by
# `deps.py` and before we checked this is a recent enough Python.

import sys


def run():
    assert sys.version_info >= (3, 10), "This MCP requires Python 3.10 or higher."

    from . import deps

    deps.ensure_sys_paths()

    from . import mcp_server

    mcp_server.run()


if __name__ == "__main__":
    run()
