import traceback
from typing import Any

from src.udbpy import ui
from src.udbpy.gdb_extensions import command

from . import deps


def load_explain(udb: object) -> None:
    deps.ensure_sys_paths()

    command.import_commands_module(udb, "explain.explain")


def patched_ui_get_user_confirmation(*args: Any, default: Any, **kwargs: Any) -> Any:
    return default


def startup(udb: object) -> None:
    try:
        # We would not have this problem with MI mode, but that would also require other changes.
        ui.get_user_confirmation = patched_ui_get_user_confirmation

        load_explain(udb)

    except BaseException as exc:
        print("Failed to load explain commands:")
        traceback.print_exc()
        raise SystemExit(1) from exc
