import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from . import xdg_dirs


repo_root = Path(__file__).resolve().parent.parent.parent


def ensure_sys_paths() -> None:
    """
    Add the dependencies directory and repo root to `sys.path`, installing dependencies if needed.
    """
    py_version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    deps_dir = xdg_dirs.get_plugin_data_dir() / f"packages-{py_version}"
    sys.path.insert(0, str(deps_dir))
    _install_deps(deps_dir)

    sys.path.insert(0, str(repo_root))


def _install_deps(deps_dir: Path) -> None:
    """
    Install dependencies from `manifest.json` to the given directory using `uv`.
    """
    # First, find out `explain`'s dependencies.
    manifest = json.loads(
        (repo_root / "private/manifest.json").read_text(encoding="utf-8"),
    )
    deps: list[str] = manifest["udb_addons"]["explain"]["python_package_deps"]

    # Then add the ones for the Claude plugin itself.
    deps.extend(
        [
            "pexpect",
            "requests",
        ]
    )

    # Skip installation if dependencies haven't changed.
    checksum_path = deps_dir / "checksum.txt"
    checksum_current = hashlib.sha224(json.dumps(deps).encode("utf-8")).hexdigest()
    try:
        checksum_last = checksum_path.read_text()
    except FileNotFoundError:
        pass
    else:
        if checksum_last == checksum_current:
            return

    deps_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        uv = os.environ["_UNDO_uv_path"]  # Set by `run.sh`.
    except KeyError as exc:
        raise RuntimeError(
            "_UNDO_uv_path not set. This module must be invoked via run.sh."
        ) from exc

    deps_cmd = [
        uv,
        "pip",
        "install",
        "--quiet",
        "--upgrade",
        "--target",
        str(deps_dir),
    ] + deps

    try:
        subprocess.check_output(
            deps_cmd,
            stderr=subprocess.STDOUT,
            text=True,
            env={
                **os.environ,
                "UV_NO_PROGRESS": "1",
            },
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to install dependencies with command {shlex.join(deps_cmd)}:\n{exc.output}"
        ) from exc

    checksum_path.write_text(checksum_current)
