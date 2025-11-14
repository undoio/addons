#!/usr/bin/env python3
"""
MCP Server for Undo recording debugging.

Provides AI-powered analysis and debugging capabilities for Undo recordings.
Tools are dynamically generated from explain.py at runtime.
"""

import shlex
import signal
import textwrap
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import controller, inspect_tools, trial


# Load tools dynamically from explain.py
_tools, _base_mcp_instructions = inspect_tools.load_tools(controller.invoke_tool)

MCP_INSTRUCTIONS = f"""
{_base_mcp_instructions}

# Undo Recordings

Undo Recordings are self-contained files that capture the complete execution history of a program
in a form that can be replayed by UDB (the debugger part of the Undo Suite) and by this MCP server
(which uses UDB).

Recordings typically have the file extension `.undo`, but that's not a requirement. You can create
recordings using the `record` MCP tool, but the user may also already have recordings they generated
in other ways.

**IMPORTANT:**
- Recordings are opaque binary files.
- You MUST never try to open or parse a recording yourself.
- If a file has `.undo` extension, you MUST assume it's a recording, so you MUST use the provided MCP
  tools to investigate it - don't try to parse it.
- Once you have a recording, you MUST use the provided MCP tools to debug it.
- Never try to invoke UDB directly as it can be controlled by this MCP server.
- Don't try to use GDB on the recordings as GDB doesn't support them.
- As recordings contain the complete execution history of a program, you MUST NOT re-run the program
  to obtain information that is already available in a recording. Re-running the program may lead to
  different behaviour.

You may see recordings referred as "Undo recordings", "LiveRecorder recordings", "LR recordings",
"UDB recordings", or "UndoDB recordings". These are all the same, but when talking about recordings
to users you MUST always use the term "Undo recordings" or just "recordings" to avoid confusion.
"""

# Initialize the MCP server with instructions
mcp = FastMCP("undo", instructions=MCP_INSTRUCTIONS)

# Register all dynamically loaded tool functions with FastMCP
for tool_name, tool_func in _tools.items():
    mcp.tool(name=tool_name)(tool_func)


@mcp.tool()
def record(command: list[str] | str, recording: Path, force: bool = False) -> str:
    """
    Record the execution of a program using live-record to create an Undo recording.

    This tool captures the complete execution history of a program, including all function
    calls, variable values, control flow, and system interactions. The resulting recording
    can be debugged using the available MCP tools or UDB directly.

    Once a recording reproducing an issue is generated, you should not re-run the program to
    investigate its behaviour as the recording already contains all the state you need.
    Re-running the program may lead to different behaviour and make debugging more difficult.

    Args:
        command: The command to execute. Can be a string (which will be shell-parsed) or
                a list of arguments (e.g., ["./program", "--flag", "value"]).
        recording: Path where the UDB recording file should be saved. Typically uses
                  the .undo extension.
        force: If False (default) and the recording file already exists, an error will be
               raised prompting you to ask the user for confirmation. If True, overwrites
               the existing file without prompting. IMPORTANT: You should NEVER set this
               to True unless explicitly instructed by the user to overwrite the file.

    Returns:
        Success message with the recording path and instructions for next steps.
    """
    if isinstance(command, str):
        command = shlex.split(command)
    ret_code = controller.record(command, recording, force)

    if ret_code < 0:
        ret_code = -ret_code
        try:
            sig_name = signal.Signals(ret_code).name
            result = f"signal {sig_name} (numeric code: {ret_code})"
        except ValueError:
            sig_name = str(ret_code)
            result = f"unknown signal {ret_code}"
        fail_reason = {
            int(signal.SIGSEGV): "crash",
            int(signal.SIGABRT): "abort",
            int(signal.SIGINT): "stop",
        }.get(ret_code, f"terminate with signal {sig_name}")
        suggestions = textwrap.dedent(
            f"""\
            - Why did the program {fail_reason}?
            - What went wrong in the recording?
            - Investigate the cause of the {fail_reason}.
            - What was the program supposed to do?"""
        )
    else:
        result = f"exit code {ret_code}"
        if ret_code > 0:
            suggestions = textwrap.dedent(
                f"""\
                - Why did the program exit with code {ret_code}?
                - What caused the failure?
                - What was the program supposed to do?"""
            )
        else:
            suggestions = ""

    return (
        textwrap.dedent(
            f"""\
            Successfully recorded program to {recording}.
            The program exited with {result}.
            The recording can now be used for debugging using the tools provided by this MCP server.

            If the user asks to debug something without explicitly mentioning the recording, assume
            that the latest generated recording is the one to debug.

            Suggest to the user some valid next steps, for instance:
            """
        )
        + suggestions
    )


@mcp.tool()
def configure_undo_path(path: Path | str | None) -> str:
    """
    Configure the path to the Undo installation directory or UDB executable.

    Args:
        path: Path to the Undo installation directory or UDB executable.
              Pass None to clear the configured path.

    Returns:
        Success message confirming the configuration.
    """
    resolved_path = controller.configure_undo_path(path)

    if resolved_path is None:
        return "Successfully cleared the configured Undo path."

    return textwrap.dedent(
        f"""\
        Successfully configured Undo path to: {resolved_path}
        Any operation that previously stopped due to a missing Undo Suite, UDB or `live-record`
        should now work, so you can resume your debugging."""
    )


@mcp.tool()
def install_trial() -> str:
    """
    Install a trial version of the Undo Suite.

    This will download and install a trial version of UDB that can be used for evaluation purposes.

    You should call this tool in response to an error indicating that Undo is not installed, but
    only if the user explicitly asks for a trial version of it.

    Returns:
        Success message with information about your next steps.
    """
    trial.install_trial(controller.get_undo_trial_dir())
    return textwrap.dedent(
        """\
        Successfully installed an Undo Suite trial. You can now continue with any operation that was
        interrupted due to a missing Undo Suite, UDB or `live-record`."""
    )


def run() -> None:
    mcp.run()
