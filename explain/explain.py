"""
AI extension for UDB, providing an MCP server and a debug assistant using with Claude Code.

Provides the commands:

 * `uexperimental mcp serve` - to expose the current session for use as an MCP server by an external
   AI client tool.
 * `explain` - to hand control to a local Claude Code and attempt to answer a question within a
   running UDB session.
"""

import asyncio
import contextlib
import functools
import inspect
import json
import os
import random
import re
import shutil
import socket
import textwrap
import time

from collections.abc import Callable
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, TypeAlias, TypeVar

import gdb

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import Prompt

from src.udbpy import textutil, ui
from src.udbpy.fileutil import mkstemp
from src.udbpy.gdb_extensions import (
    command,
    command_args,
    gdbio,
    gdbutils,
    udb_base,
    udb_last,
)
from src.udbpy.termstyles import ansi_format, Color, Intensity


import uvicorn.server

# Prevent uvicorn trying to handle signals that already have special GDB handlers.
uvicorn.server.HANDLED_SIGNALS = ()

# Switch the debug level to get more context if the MCP server is misbehaving.
LOG_LEVEL = "CRITICAL"
# LOG_LEVEL="DEBUG"


EXTENSION_PATH = Path(__file__).parent
"""Directory containing this extension module."""

MCP_INSTRUCTIONS = (EXTENSION_PATH / "instructions.md").read_text(encoding="UTF-8")
"""Top-level instructions for the MCP server."""

SYSTEM_PROMPT = (EXTENSION_PATH / "system_prompt.md").read_text(encoding="UTF-8")
"""System prompt to supply to Claude on every invocation."""

THINKING_MSGS = (EXTENSION_PATH / "thinking.txt").read_text(encoding="UTF-8").split("\n")[:-1]
"""Messages to display whilst the system is thinking."""

CLAUDE_LOCAL_INSTALL_PATH = Path.home() / ".claude" / "local" / "claude"

P = ParamSpec("P")
T = TypeVar("T")
UdbMcpGatewayAlias: TypeAlias = "UdbMcpGateway"


# Something in the webserver stack holds onto a reference to the event loop
# after shutting down. It's easier to just using the same event loop for each
# invocation.
event_loop = None

claude_session = None
"""Claude session, if an interaction has already begun."""


def console_whizz(msg: str, end: str = "\n") -> None:
    """
    Animated console display for major headings.
    """
    for c in msg:
        print(
            ansi_format(c, foreground=Color.GREEN, intensity=Intensity.BOLD),
            end="",
            flush=True,
        )
        time.sleep(0.01)
    print(end=end)


def print_report_field(label: str, msg: str) -> None:
    """
    Formatted field label for reporting command results.
    """
    label_fmt = ansi_format(f"{label + ':':10s}", foreground=Color.WHITE, intensity=Intensity.BOLD)
    print(f" | {label_fmt} {msg}")


def print_divider() -> None:
    """
    Display a divider between output elements.
    """
    print(" |---")


def report(fn: Callable[P, str | None]) -> Callable[P, str]:
    """
    Wrap a tool to report on the current thinking state (if appropriate) and result.
    """

    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        formatted_name = fn.__name__.removeprefix("tool_").replace("_", "-")
        print_report_field("Operation", f"{formatted_name:15s}")

        sig = inspect.signature(fn)
        binding = sig.bind(*args, **kwargs)
        hypothesis = binding.arguments.pop("hypothesis")  # We'll report this one separately.
        arguments = ", ".join(f"{k}={v}" for k, v in binding.arguments.items() if k != "self")
        if arguments:
            print_report_field("Arguments", arguments)
        print_report_field("Thoughts", hypothesis)

        # Present result in a compact form if it's a single line, otherwise use multiple lines.
        try:
            results = fn(*args, **kwargs)
        except Exception as e:
            results = str(e)
            raise e
        finally:
            if results is None:
                results = ""

            if len(results.splitlines()) == 1:
                result_text = results
            else:
                result_text = "\n" + textwrap.indent(results, "   $  ", predicate=lambda _: True)

            print_report_field("Result", result_text)
            print_divider()
        return results

    return wrapped


def collect_output(fn: Callable[P, None]) -> Callable[P, str]:
    """
    Collect GDB's output during the execution of the wrapped function.

    Used to pass back interactive output directly to the LLM.
    """

    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        with gdbio.CollectOutput() as collector:
            fn(*args, **kwargs)

        return collector.output

    sig = inspect.signature(fn)
    wrapped.__signature__ = sig.replace(return_annotation=str)  # type: ignore

    return wrapped


SOURCE_CONTEXT_LINES = 5
"""The maximum size of source context to show either side of the current position."""


@functools.cache
def get_substitute_paths() -> list[tuple[Path, Path]]:
    """
    Query substitute path settings from the debugger.
    """
    out = gdbutils.execute_to_string("show substitute-path")
    path_re = re.compile(r"\s+`(?P<in_prefix>[^']+)' -> `(?P<out_prefix>[^']+)'")

    path_map: list[tuple[Path, Path]] = []
    for l in out.splitlines():
        m = path_re.match(l)
        if not m:
            continue
        path_map.append((Path(m["in_prefix"]), Path(m["out_prefix"])))

    return path_map


def get_path(fname: str) -> Path:
    """
    Get the real filesystem path for a named file, taking into account substitutions.
    """
    p = Path(fname)
    for in_path, out_path in get_substitute_paths():
        if p.is_relative_to(in_path):
            rel_path = p.relative_to(in_path)
            return out_path.joinpath(rel_path)
    return Path(fname)


def get_context(fname: str, line: int) -> str:
    """
    Return formatted file context surrounding the current debug location.
    """
    f = get_path(fname)
    try:
        lines = Path(f).read_text(encoding="UTF-8").split("\n")
    except FileNotFoundError:
        return ""

    start_line = max(0, line - SOURCE_CONTEXT_LINES)
    end_line = min(len(lines), line + SOURCE_CONTEXT_LINES)

    formatted_lines = list(
        f" {'->' if i == line - 1 else '  '} {i + 1: 5d} {lines[i].rstrip()}"
        for i in range(start_line, end_line)
    )

    return "\n".join(formatted_lines)


def source_context(fn: Callable[P, str]) -> Callable[P, str]:
    """
    Add source location context to the result of a wrapped function.

    This informs the LLM of the current source context when the command returns, useful when a
    command moves through debug history.
    """

    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        out = fn(*args, **kwargs)

        frame = gdb.selected_frame()
        sal = frame.find_sal()

        context = f"\nFunction: {frame.name()}\n"

        source = None
        if sal and sal.symtab:
            source = get_context(sal.symtab.filename, sal.line)

        if source:
            context += "\nSource context:\n" + source
        else:
            context += "\nSource context unavailable."

        return out + context

    return wrapped


def chain_of_thought(
    fn: Callable[Concatenate[UdbMcpGatewayAlias, P], T],
) -> Callable[Concatenate[UdbMcpGatewayAlias, str, P], T]:
    """
    Add chain-of-thought parameters and documentation to the wrapped function.

    This requires the LLM to explain its reasoning as it goes along, leading to better or more
    understandable results.
    """

    @functools.wraps(fn)
    def wrapped(self, hypothesis: str, *args: Any, **kwargs: Any):
        # pylint: disable=unused-argument
        return fn(self, *args, **kwargs)

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    hypothesis_param = inspect.Parameter(
        "hypothesis", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str
    )
    params.insert(1, hypothesis_param)

    wrapped.__signature__ = sig.replace(parameters=params)  # type: ignore

    assert wrapped.__doc__
    wrapped.__doc__ += """
        Additional parameters:
        hypothesis -- describe the hypothesis you are currently investigating.
    """

    return wrapped


def revert_time_on_failure(
    fn: Callable[Concatenate[UdbMcpGatewayAlias, P], T],
) -> Callable[Concatenate[UdbMcpGatewayAlias, P], T]:
    """
    Decorator to ensure a tool does not change debugger time if an exception is thrown.
    """

    @functools.wraps(fn)
    def wrapped(self, *args: Any, **kwargs: Any):
        t = self.udb.time.get_bookmarked()
        try:
            return fn(self, *args, **kwargs)
        except:
            # Revert time on failure so failed tool invocations don't affect state.
            self.udb.time.goto(t)
            raise

    return wrapped


class UdbMcpGateway:
    """
    Plumbing class to expose selected UDB functionality as a set of tools to an MCP server.

    The operations exposed are chosen to be well-suited to use by an LLM. For now, that means that
    only reverse operations are supported (to impose reverse debugging practices on the LLM) and
    that unnecessary (or potentially distracting) operations are not exposed.
    """

    def __init__(self, udb: udb_base.Udb):
        self.udb = udb
        self.mcp = FastMCP("UDB_Server", instructions=MCP_INSTRUCTIONS, log_level=LOG_LEVEL)
        self.tools: list[str] = []
        self._register_tools()

    def _register_tools(self) -> None:
        for name, fn in inspect.getmembers(self, inspect.ismethod):
            if name.startswith("tool_"):
                name = name.removeprefix("tool_")
                self.tools.append(name)
                self.mcp.add_tool(fn=fn, name=name, description=fn.__doc__)
            elif name.startswith("prompt_"):
                name = name.removeprefix("prompt_")
                prompt = Prompt.from_function(fn, name=name, description=fn.__doc__)
                self.mcp.add_prompt(prompt)
            else:
                continue

    def prompt_explain(self, question):
        """
        Answer a user's question about the code.
        """
        return "\n".join([SYSTEM_PROMPT, question])

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_ugo_end(self) -> None:
        """
        Go to the end of recorded history.

        The end of recorded history is a good place from which to begin investigating a bug.

        If you get lost or see inconsistent state then return to the end and begin investigations
        again.
        """
        self.udb.time.goto_end()

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_last_value(self, expression: str) -> None:
        """
        Wind back time to the last time an expression was modified.

        This should NOT be used with function call expressions e.g. my_function(number) as
        it will be very slow.

        This should NOT be used for address-taken expressions, such as &variable_name, since this
        will be very slow and won't give a meaningful answer.

        This should NOT be used for debugger convenience variables (starting with a $), since this
        will be very slow.

        Use expressions that are based solely on variables or memory locations.
        """
        self.udb.last.execute_command(
            expression, direction=udb_last.Direction.BACKWARD, is_repeated=False
        )

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_next(self) -> None:
        """
        Run backwards to the previous line of source code, stepping over function calls.

        Run this to move upwards in the source code or to get to just below a call to a
        function you will `reverse_step` into.
        """
        self.udb.execution.reverse_next(cmd="reverse-next")

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_finish(self) -> None:
        """
        Run backwards to before the current function was called.
        """
        self.udb.execution.reverse_finish(cmd="reverse-finish")

    @report
    @source_context
    @revert_time_on_failure
    @chain_of_thought
    def tool_reverse_step_into_current_line(self, target_fn: str) -> str:
        """
        Reverse into a function call on the current line of the program.

        The current line must contain a function call.

        Params:
        target_fn: the function you want to step into
        """
        # LLMs prefer to step backwards into a function on the current line,
        # rather than reverse up to that line and then step in.
        #
        # Also, it's possible that there are multiple functions to step into on
        # a given line (either because the calls are nested or because there
        # are multiple in sequence).
        #
        # To handle these cases, we ask the LLM what function it wants, then:
        #  * Step forward past the current line.
        #  * Set a breakpoint on the start of the target function.
        #  * Run back to it.
        #  * Use "finish" to get out (grabbing the return value as we go).
        #  * Use "reverse-step" to get back into the end of the function.

        # Step to next line.
        self.udb.execution.next()

        # Now try to step back into the correct function.
        with gdbutils.temporary_breakpoints(), gdbio.CollectOutput() as collector:
            # Create a breakpoint on the start of the target function.
            target_start_bp = gdb.Breakpoint(target_fn, internal=True)
            thread = gdb.selected_thread()
            assert thread is not None
            target_start_bp.thread = thread.global_num
            assert target_start_bp.is_valid()

            while not target_start_bp.hit_count:
                if self.udb.get_undodb_info().flags.at_event_log_start:
                    raise Exception(f"Failed to reverse step into function {target_fn}.")
                self.udb.execution.reverse_cont()

            # Check we really got to the function we intended.
            assert gdb.selected_frame().name() == target_fn

            # We're at the start of the target function, now we need to get to the end.
            self.udb.execution.finish()
            return_value = gdb.parse_and_eval("$")

            # Step back into the end of the function.
            self.udb.execution.reverse_step(cmd="reverse-step")

            # Check that we got back into the function we intended.
            assert gdb.selected_frame().name() == target_fn

        if LOG_LEVEL == "DEBUG":
            print(f"reverse_step_into_current_line internal messages:\n{collector.output}")

        return f"{target_fn} return value: {return_value}"

    @report
    @chain_of_thought
    def tool_backtrace(self) -> str:
        """
        Get a backtrace of the code at the current point in time.
        """
        return gdbutils.execute_to_string("backtrace")

    @report
    @chain_of_thought
    def tool_print(self, expression: str) -> str:
        """
        Get the value of an expression.

        This should NOT be used to retrieve the value of GDB value history
        variables such as $0, $1, $2, etc.

        Do NOT use the C comma "," operator to attempt to print multiple values. This will produce
        misleading output. To print multiple values you should call the `print` tool once for each.

        Params:
        expression -- the expression to be evaluated.
        """
        return str(gdb.parse_and_eval(expression))

    @report
    @chain_of_thought
    def tool_ubookmark(self, name) -> None:
        """
        Set a bookmark at the current point in time.

        Use this when you have identified an interesting point in time during the debug session.

        Params:
        name - a descriptive name for the current point of interest.
        """
        self.udb.bookmarks.add(name)

    @report
    @chain_of_thought
    def tool_info_bookmarks(self) -> str:
        """
        Returns the names of previously-stored bookmarks.

        Use this to query interesting points in time that are already identified.
        """
        return "\n".join(self.udb.bookmarks.iter_bookmark_names())

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_ugo_bookmark(self, name) -> None:
        """
        Travels to the time of a named bookmark that was previously set.

        You can only use this for bookmarks that you have previously set using
        `ubookmark` or that appear in the output of `info_bookmarks`.

        Use this to investigate further from an interesting point in time.
        """
        self.udb.bookmarks.goto(name)


command.register_prefix(
    "uexperimental mcp",
    gdb.COMMAND_NONE,
    """
    Experimental commands for managing MCP integration.
    """,
)


def run_server(gateway: UdbMcpGateway, port: int) -> None:
    """
    Run an MCP server until interrupted or otherwise shut down.
    """
    global event_loop
    if not event_loop:
        event_loop = asyncio.new_event_loop()

    sock = None
    server = None
    mcp_task = None
    try:
        sock = socket.create_server(("localhost", port))

        # Set up a temporary MCP server for this UDB session.
        starlette_app = gateway.mcp.sse_app()
        config = uvicorn.Config(starlette_app, log_level=LOG_LEVEL.lower())
        server = uvicorn.Server(config)
        mcp_task = event_loop.create_task(server.serve(sockets=[sock]))

        print(f"MCP server running on http://localhost:{port}/sse")
        print(
            f"Use ^C to stop and return to the UDB prompt "
            f"(this will break the connection to your MCP client)."
        )
        event_loop.run_until_complete(mcp_task)

    finally:
        # Shut down the server once we have an explanation.
        if server:
            server.should_exit = True
        if server and mcp_task:
            tasks = asyncio.all_tasks(loop=event_loop)
            for t in tasks:
                t.cancel()
            event_loop.run_until_complete(asyncio.wait([server.shutdown()] + list(tasks)))
        if sock:
            sock.close()


@command.register(
    gdb.COMMAND_USER,
    arg_parser=command_args.DashArgs(
        command_args.Option(
            long="port",
            short="p",
            value=command_args.Integer(purpose="port", default=8000, minimum=0),
        ),
    ),
)
def uexperimental__mcp__serve(udb: udb_base.Udb, args: Any) -> None:
    """
    Start an MCP server for this UDB instance.
    """
    gateway = UdbMcpGateway(udb)
    with (
        gdbutils.temporary_parameter("pagination", False),
        udb.replay_standard_streams.temporary_set(False),
        gdbutils.breakpoints_suspended(),
    ):
        run_server(gateway, args.port)


def print_assistant_message(text: str):
    """
    Display a formatted message from the code assistant.
    """
    field = "Assistant"
    # Effective width = terminal width - length of formatted field - additional chars
    single_line_width = textutil.TERMINAL_WIDTH - 14
    if len(text.splitlines()) > 1 or len(text) >= single_line_width:
        prefix = "   >  "
        # If we wrap, we'll start a new line and the width available is different.
        wrapping_width = textutil.TERMINAL_WIDTH - len(prefix)
        text = "\n".join(
            textwrap.wrap(
                text,
                width=wrapping_width,
                drop_whitespace=False,
                replace_whitespace=False,
            )
        )
        text = "\n" + textwrap.indent(text, prefix=prefix, predicate=lambda _: True)
    print_report_field(field, text)
    print_divider()


async def handle_claude_messages(stdout) -> str:
    """
    Handle streamed JSON messages from Claude until a final result, which is returned.
    """
    result = ""

    async for line in stdout:
        msg = json.loads(line)
        if LOG_LEVEL == "DEBUG":
            print("Message:", msg)

        if msg.get("type") == "result":
            # Fetch the session ID so that we can resume our conversation next time.
            global claude_session
            claude_session = msg["session_id"]

            # Stash the result so that we can print our overall explanation.
            result = msg["result"]

            # This should be the last message in the stream, allow us to fall out of the loop
            # naturally and return it.
            continue

        if msg.get("type") != "assistant":
            # We only need to report things the code assistant did.
            continue

        # Gather relevant content for display (if any).
        content = msg.get("message").get("content", [])
        display_content = []
        for c in content:
            match c:
                case {"type": "text", "text": text}:
                    display_content.append(text)
                case {"type": "tool_use", "name": tool_name} if not tool_name.startswith(
                    "mcp__UDB_Server"
                ):
                    # Report use of other tools.
                    args = "\n".join(f"    {k}='{v}'" for k, v in c.get("input").items())
                    display_content.append(f"Tool use: {tool_name}\n{args}")

        if not display_content:
            # Nothing interesting to say.
            continue

        assistant_text = "\n".join(display_content)
        # Print an interim assistant message.
        print_assistant_message(assistant_text)

    return result


async def ask_claude(claude_bin: Path, why: str, port: int, tools: list[str]) -> str:
    """
    Pose a question to an external `claude` program, supplying access to a UDB MCP server.
    """
    if LOG_LEVEL == "debug":
        print(f"Connecting Claude to MCP server on port {port}")
    else:
        console_whizz(f" * {random.choice(THINKING_MSGS)}...")
        print_divider()

    mcp_config = {
        "mcpServers": {"UDB_Server": {"type": "sse", "url": f"http://localhost:{port}/sse"}}
    }
    mcp_config_fd, mcp_config_path = mkstemp(prefix="mcp_config", suffix=".json")
    with contextlib.closing(os.fdopen(mcp_config_fd, "w")) as mcp_config_file:
        json.dump(mcp_config, mcp_config_file)

    allowed_tools = ",".join(f"mcp__UDB_Server__{t}" for t in tools)

    result = ""
    try:
        claude = await asyncio.create_subprocess_exec(
            str(claude_bin),
            *(["--resume", claude_session] if claude_session else []),
            "--model",
            "opus",
            "--mcp-config",
            mcp_config_path,
            "--allowedTools",
            allowed_tools,
            "--output-format",
            "stream-json",
            "--verbose",  # Required for --output-format stream-json
            "-p",
            why,
            "--system-prompt",
            SYSTEM_PROMPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert claude.stdout and claude.stderr

        result = await handle_claude_messages(claude.stdout)

        stderr = await claude.stderr.read()
        if stderr:
            print("Errors:\n", stderr)

    finally:
        # Make sure Claude is properly cleaned up if we exited early.
        if claude.returncode is None:
            claude.terminate()
            await claude.wait()

    return result


async def explain_query(claude_bin: Path, gateway: UdbMcpGateway, why: str) -> str:
    """
    Explain a query from the user using an external `claude` process + MCP.
    """
    sock = None
    server = None
    mcp_task = None
    try:
        sock = socket.create_server(("localhost", 0))
        _, port = sock.getsockname()

        # Set up a temporary MCP server for this UDB session.
        starlette_app = gateway.mcp.sse_app()
        config = uvicorn.Config(starlette_app, log_level=LOG_LEVEL.lower())
        server = uvicorn.Server(config)
        mcp_task = asyncio.create_task(server.serve(sockets=[sock]))

        # Ask Claude the question.
        explanation = await ask_claude(claude_bin, why, port, tools=gateway.tools)

    finally:
        # Shut down the server once we have an explanation.
        if server:
            server.should_exit = True
            await server.shutdown()
        if mcp_task:
            await mcp_task
        if sock:
            sock.close()

    return explanation


@command.register(gdb.COMMAND_USER, arg_parser=command_args.Untokenized())
def explain(udb: udb_base.Udb, why: str) -> None:
    """
    Use AI to answer questions about the code.
    """
    claude_bin = None
    if loc := shutil.which("claude"):
        claude_bin = Path(loc)
    elif CLAUDE_LOCAL_INSTALL_PATH.exists():
        claude_bin = CLAUDE_LOCAL_INSTALL_PATH

    if not claude_bin:
        print("Could not find `claude`.")
        print("Please ensure working install of Claude Code is available on your PATH.")
        return

    if not why:
        print("Enter your question (type ^D on a new line to exit):")
        with contextlib.suppress(EOFError):
            while True:
                why += ui.get_user_input(prompt="> ") + "\n"
        print()

    gateway = UdbMcpGateway(udb)

    global event_loop
    if not event_loop:
        event_loop = asyncio.new_event_loop()

    # Don't allow debuggee standard streams or user breakpoints, they will confuse the LLM.
    with (
        gdbutils.temporary_parameter("pagination", False),
        udb.replay_standard_streams.temporary_set(False),
        gdbutils.breakpoints_suspended(),
    ):
        explanation = event_loop.run_until_complete(explain_query(claude_bin, gateway, why))

    console_whizz(" * Explanation:")
    print(textwrap.indent(explanation, "   =  ", predicate=lambda _: True))
