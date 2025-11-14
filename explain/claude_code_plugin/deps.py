import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from . import xdg_dirs


# IMPORTANT: only import standard library modules or modules with a similar warning here as this
# code must run before dependencies are installed.


repo_root = Path(__file__).resolve().parent.parent.parent


def ensure_sys_paths() -> None:
    deps_dir = xdg_dirs.get_plugin_data_dir() / "packages"
    sys.path.insert(0, str(deps_dir))
    _install_deps(deps_dir)

    sys.path.insert(0, str(repo_root))


def _install_deps(deps_dir: Path) -> None:
    # First get `explain`'s dependencies.
    manifest = json.loads(
        (repo_root / "private/manifest.json").read_text(encoding="utf-8"),
    )
    deps = manifest["udb_addons"]["explain"]["python_package_deps"]
    assert isinstance(deps, list)

    # Then add the ones for the Claude plugin itself.
    deps.extend(
        [
            "pexpect",
            "requests",
        ]
    )

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

    _run_install_command(
        [
            sys.executable,
            "-m",
            "ensurepip",
        ]
    )

    deps_cmd = [
        sys.executable,
        "-s",  # Don't use user site packages.
        "-m",
        "pip",
        "-q",
        "install",
        "--ignore-installed",  # Ignore what may be installed in the system.
        "--upgrade",
        "--target",
        ".",
    ] + deps
    _run_install_command(deps_cmd, cwd=deps_dir)

    checksum_path.write_text(checksum_current)


def _run_install_command(cmd: list[str], *, cwd: Path | None = None) -> None:
    try:
        subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            env={
                **os.environ,
                "PIP_NO_WARN_SCRIPT_LOCATION": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            },
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to install dependencies with command {shlex.join(cmd)}:\n{exc.output}"
        ) from exc
