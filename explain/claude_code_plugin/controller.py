import functools
import json
import os
import platform
import re
import shutil
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import Any

import pexpect

from . import deps, xdg_dirs


def get_configuration_file_path() -> Path:
    """
    Get the path to the configuration file for the plugin.
    """
    return xdg_dirs.get_plugin_data_dir() / "undo_path.txt"


def get_configured_undo_dir() -> Path | None:
    """
    Return the configured Undo path from the configuration file, or `None` if not set or invalid.
    """
    try:
        udb_path = Path(get_configuration_file_path().read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError):
        return None

    return udb_path if os.access(udb_path, os.X_OK) else None


# Note that this mentions "path" rather than "dir" like in `get_configured_undo_dir` on purpose,
# as it accepts a file path as well.
def configure_undo_path(undo_path: Path | str | None) -> Path | None:
    """
    Validate and save the path to the Undo installation so it can be used later for debugging or
    generating recordings.

    If `undo_path` is `None`, clears the configured path.
    """
    config_path = get_configuration_file_path()

    if undo_path is None:
        # Clear the configuration by removing the file.
        config_path.unlink(missing_ok=True)
        return None

    undo_path = Path(undo_path).expanduser().resolve()
    if (
        undo_path.is_file()
        and os.access(undo_path, os.X_OK)
        and undo_path.name in ("udb", "live-record")
    ):
        # The user passed the path to UDB/live-record, not the directory.
        undo_path = undo_path.parent

    if not os.access(undo_path, os.X_OK):
        raise ValueError(f"{undo_path} is not a valid executable")
    config_path.write_text(str(undo_path), encoding="utf-8")

    return undo_path


def get_undo_trial_dir() -> Path:
    """
    Return the path to the location where an Undo trial is or should be installed.

    The directory may not exist if the trial has not been installed.
    """
    return xdg_dirs.get_plugin_data_dir() / "udb_trial"


class ToolNotFoundError(RuntimeError):
    """
    Exception raised when a required tool is not found.
    """


def ensure_undo_tool(tool: str) -> Path:
    if platform.system() != "Linux":
        raise RuntimeError(
            f"Undo is only supported on Linux. Current platform: {platform.system()}"
        )

    for path_fn in (
        get_configured_undo_dir,
        functools.partial(shutil.which, tool),
        get_undo_trial_dir,
    ):
        path = path_fn()
        if path is None:
            continue
        path = Path(path)
        if path.is_dir():
            path = path / tool
        if path.is_file():
            return path

    raise ToolNotFoundError(
        textwrap.dedent(
            f"""\
            {tool!r} was not found on the `$PATH`. You MUST stop and ask the user to either:
            1. Provide the path to their Undo installation
            2. Request an installation of a Undo trial license

            For instance, you could present the user with the following message:

                The {tool!r} tool was not found on your system. To proceed you can:
                1. Tell me the correct path to your Undo installation
                2. Ask me to install a trial version of the Undo Suite for you

            If the user chooses to provide the installation path, you MUST call the
            `configure_undo_path` MCP tool with that path (and only the path).

            If the user chooses to request a trial installation, you MUST call the `install_trial`
            MCP tool (with no arguments).

            Once either of these actions have been taken, you MUST call this function again."""
        )
    )


def gdb_command_arg_escape(unescaped: str | Path) -> str:
    """
    Returns an escaped version of `unescaped` suitable for passing to a GDB command.

    `unescaped` can be a :class:`str`, or for the calling code's convenience, a :class:`Path`.

    GDB uses its own idiosyncratic escape logic, so you must use this function
    and not `shlex.quote` to escape a string.

    UDB commands need their arguments to be escaped, but this is not true for
    all built-in GDB commands. GDB commands that take multiple arguments (for
    example, "add-symbol-file", "remote get") need the arguments to be escaped.
    GDB commands that take a single argument sometimes need that argument
    escaping, but sometimes not. There is no alternative to checking the command
    yourself and then updating this docstring.
    """
    unescaped = str(unescaped)

    if not unescaped:
        # Make sure we get a token for the unescaped argument.
        return "''"

    # Escape characters that are treated specially by buildargv() in GDB's
    # libiberty/argv.c: that is, ASCII whitespace, double quote, single quote,
    # and backslash.
    return re.sub(r"[\t\n\v\f\r \"'\\]", r"\\\g<0>", unescaped)


# When using styled text as prompt in a program using readline, readline counts ANSI escape codes
# as part of the string length. To avoid this it's possible to mark a part of a string as invisible
# to readline by surrounding it by these special characters.
# See readline.h for where these values are defined as RL_PROMPT_START_IGNORE and
# RL_PROMPT_END_IGNORE.
_READLINE_PROMPT_START_IGNORE = "\001"
_READLINE_PROMPT_END_IGNORE = "\002"
# Regular expression to identify ANSI escape codes.
_STYLE_RE = f"\N{ESCAPE}\\[.*?m|{_READLINE_PROMPT_START_IGNORE}|{_READLINE_PROMPT_END_IGNORE}"


def strip_ansi_escape_codes(source: str) -> str:
    """
    Return the input string with ANSI escape codes and readline characters removed.
    """
    return re.sub(_STYLE_RE, "", source)


class UdbHarness:
    def __init__(self, udb_path: Path) -> None:
        self._udb_path = udb_path
        self._prompt = f"<PROMPT {uuid.uuid4().hex}>"
        self._child = pexpect.spawn(
            str(udb_path),
            [
                "--quiet",
                # Disable prompts. We should probably use MI mode, but for now it's easier to just
                # use UDB in normal mode.
                "--startup-prompt=none",
                "--print-python-stack=full",
                "--init-eval-command",
                "set debuginfod enabled on",
                "--init-eval-command",
                "set style enabled off",
                "--sessions",
                "no",
                "--init-eval",
                f"set prompt {self._prompt}",
                "--init-eval-command",
                (
                    f"python "
                    f"sys.path.insert(0, {str(deps.repo_root)!r}); "
                    f"from explain.claude_code_plugin.udb_startup import startup as _run_startup; "
                    f"_run_startup(_udb)"
                ),
            ],
            encoding="utf-8",
            codec_errors="backslashreplace",
        )
        self._wait_prompt()
        startup_output = self._child.before or ""

        token = f"{uuid.uuid4().hex}"
        try:
            output = self.do(f"uinternal mcp self-check {token}", timeout=5)
        except pexpect.TIMEOUT as exc:
            raise RuntimeError(
                f"UDB harness self-check timed out with output:\n"
                f"{startup_output}{self._whole_pexpect_buffer}"
            ) from exc
        assert f"Self check token: {token}\n" in output, (
            f"UDB harness self-check failed: expected {token!r}, got:\n"
            f"{textwrap.indent(output, ' ' * 4)}\n"
            f"With full output:\n{startup_output}{self._whole_pexpect_buffer}"
        )

    @property
    def is_trial(self) -> bool:
        return get_undo_trial_dir() in self._udb_path.parents

    @property
    def _whole_pexpect_buffer(self) -> str:
        output = (
            (self._child.before or "")
            + (self._child.after if isinstance(self._child.after, str) else "")
            + self._child.buffer
        ) or "<no output>"
        return textwrap.indent(output, " " * 4)

    def _wait_prompt(self, timeout: float | None = None) -> None:
        i = self._child.expect(
            [
                pexpect.EOF,
                self._prompt,
                pexpect.TIMEOUT,
            ],
            timeout=timeout,
        )

        if not i:
            output = self._whole_pexpect_buffer

            if "The license was expired" in output:
                if self.is_trial:
                    # Don't include the path here as it's a path we handle ourselves.
                    raise RuntimeError(
                        textwrap.dedent(
                            """\
                            The UDB trial license expired.

                            You MUST:
                            - Tell the user to visit https://undo.io/pricing-licensing/ to obtain a
                              full license and then call `/undo:configure_undo_path` to configure
                              the UDB path.
                            - You must not suggest the user to install another trial license, as
                              that will not work."""
                        )
                    )
                raise RuntimeError(
                    textwrap.dedent(
                        f"""\
                        The UDB license for the Undo Suite at {self._udb_path} has expired.

                        You MUST tell the user to either:
                        - Contact support@undo.io if they want to extend their license.
                        - Alternatively, use `/undo:configure_undo_path` to configure a different
                          Undo Suite path."""
                    )
                )

            raise RuntimeError(f"UDB exited unexpectedly with output:\n{output}")

    def do(self, command: str, timeout: float | None = None) -> str:
        self._child.sendline(command)
        self._wait_prompt(timeout=timeout)
        assert self._child.before is not None, (
            f"Unset pexpect object 'before' despite matching prompt. "
            f"Full output:\n{self._whole_pexpect_buffer}"
        )
        result = strip_ansi_escape_codes(self._child.before.replace("\r\n", "\n"))
        return result.removeprefix(f"{command}\n")


_udb: UdbHarness | None = None


def invoke_tool(tool_name: str, recording_path: str, **kwargs: object) -> Any:
    global _udb
    if _udb is None:
        _udb = UdbHarness(ensure_undo_tool("udb"))

    separator_id = uuid.uuid4().hex
    start = f"=={separator_id}:START=="
    end = f"=={separator_id}:END=="

    output = _udb.do(
        f"uinternal mcp invoke-tool "
        + " ".join(
            gdb_command_arg_escape(part)
            for part in (tool_name, start, end, recording_path, json.dumps(kwargs))
        )
    )

    match = re.search(rf"{re.escape(start)}\n(.*)\n{re.escape(end)}", output, re.DOTALL)
    if match is None:
        raise RuntimeError(f"Tool invocation failed:\n{output}")

    tool_output = match[1].strip()
    if not tool_output:
        raise RuntimeError(f"Tool invocation returned no output:\n{output}")

    try:
        return json.loads(tool_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Tool invocation returned invalid JSON:\n{tool_output}") from exc


def record(target_command: list[str], recording: Path, force: bool = False) -> int:
    """
    Record the execution of a program using `live-record` to create a UDB recording.

    Args:
        target_command: The command to execute as a list of arguments (e.g., ["./program", "arg1"]).
               The first argument for the command MUST be the actual ELF executable to record, not
               a shell wrapper or another command. For instance, `["./my_command", "arg1"]` is
               valid, but `["timeout", "5", "./my_command", "arg1"]` or `["/bin/sh", "-c",
               "./my_command arg1"]` are not).
        recording: The path where the UDB recording should be saved.
        force: If False and the recording file already exists, raises an exception asking the user
               for confirmation. If True, overwrites the existing file without prompting.
    """
    if recording.exists() and not force:
        raise RuntimeError(
            f"Recording file {recording} already exists. "
            f"Ask the user if they want to overwrite it. "
            f"If yes, call this tool again with force=true."
        )

    try:
        lr_path = ensure_undo_tool("live-record")
    except ToolNotFoundError:
        if udb := ensure_undo_tool("udb"):
            raise RuntimeError(
                textwrap.dedent(
                    f"""\
                    `live-record` is not available in {udb.parent}.
                    Either your Undo Suite doesn't include LiveRecorder, or the configured directory
                    is incorrect. Ask the user to use `/undo:configure_undo_path` to configure a
                    different Undo installation that includes LiveRecorder."""
                )
            ) from None
        raise

    lr_command = [str(lr_path), "--recording-file", str(recording)] + target_command
    proc = subprocess.run(
        lr_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="backslashreplace",
        check=False,  # LR exists with the error code from the recorded program.
    )
    if not recording.is_file():
        raise RuntimeError(
            f"Recording file {recording} was not created, despite `live-record` succeeding. "
            f"Output:\n{proc.stdout}"
        )
    return proc.returncode
