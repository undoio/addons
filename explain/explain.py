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
import random
import re
import socket
import unittest.mock
from collections.abc import Callable
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, TypeAlias, TypeVar

import gdb
import uvicorn.server
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import Prompt
from src.udbpy import engine, event_info, ui
from src.udbpy.gdb_extensions import command, command_args, gdbio, gdbutils, udb_base, udb_last

# Agent modules are imported to trigger registration.
from .agents import AgentRegistry, BaseAgent
from .amp_agent import AmpAgent  # pylint: disable=unused-import
from .assets import MCP_INSTRUCTIONS, SYSTEM_PROMPT, THINKING_MSGS
from .claude_agent import ClaudeAgent  # # pylint: disable=unused-import
from .codex_agent import CodexAgent  # pylint: disable=unused-import
from .output_utils import console_whizz, print_agent, print_explanation, print_tool_call

# Prevent uvicorn trying to handle signals that already have special GDB handlers.
uvicorn.server.HANDLED_SIGNALS = ()

# Switch the debug level to get more context if the MCP server is misbehaving.
LOG_LEVEL = "CRITICAL"
# LOG_LEVEL="DEBUG"


P = ParamSpec("P")
T = TypeVar("T")
UdbMcpGatewayAlias: TypeAlias = "UdbMcpGateway"


# Something in the webserver stack holds onto a reference to the event loop
# after shutting down. It's easier to just using the same event loop for each
# invocation.
event_loop = None


agent: BaseAgent | None = None
"""Agent instance for the current session."""


def report(fn: Callable[P, str | None]) -> Callable[P, str]:
    """
    Wrap a tool to report on the current thinking state (if appropriate) and result.
    """

    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        tool_name = fn.__name__.removeprefix("tool_").replace("_", "-")

        sig = inspect.signature(fn)
        binding = sig.bind(*args, **kwargs)
        hypothesis = binding.arguments.pop("hypothesis")  # We'll report this one separately.
        binding.arguments.pop("self")
        with print_tool_call(tool_name, hypothesis, binding.arguments) as tool_call:
            try:
                results = fn(*args, **kwargs)
            except Exception as e:
                results = str(e)
                raise e
            finally:
                if results is None:
                    results = ""

                tool_call.report_result(results.rstrip())

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
    def wrapped(self, *args: Any, **kwargs: Any):
        out = fn(self, *args, **kwargs)

        frame = gdb.selected_frame()
        sal = frame.find_sal()

        context = f"\nFunction: {frame.name()}\n"

        if bookmarks := self.udb.bookmarks.get_at_time(self.udb.time.get()):
            context += f"\nAt bookmarks: {', '.join(bookmarks)}\n"

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
    def tool_ugo_sender(self) -> None:
        """
        Switch to another available recording (if present) at the point that sent data to the
        program currently running.

        You should use this tool if you believe a bug involves a bad value received from another
        process.  Confirm why the bad value arrived before reporting a result.

        After using this tool, debugging will resume in the context of the sending process not the
        one you have been debugging.  You will need to refresh your state.

        Do not use the ugo_end tool afterwards as this will skip past the point of interest.
        """
        entry = self.udb.multiproc.find_correlated_entry_for_previous_entry(
            self.udb.inferiors.selected, True
        )
        self.udb.inferiors.goto_inferior_num(entry.inferior.num)
        self.udb.events.goto_event_time(engine.Time(entry.bbcount, event_info.PC_AFTER_BB))

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
        with gdbio.CollectOutput() as collector:
            self.udb.execution.next()
        if LOG_LEVEL == "DEBUG":
            print(f"reverse_step_into_current_line internal step to next line: {collector.output}")

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
        if clashes := self.udb.bookmarks.get_at_time(self.udb.time.get()):
            raise Exception(f"This time is already bookmarked: {', '.join(clashes)}")
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
        unittest.mock.patch.object(udb, "_volatile_mode_explained", True),
    ):
        run_server(gateway, args.port)


async def explain_query(agent: BaseAgent, gateway: UdbMcpGateway, why: str) -> str:
    """
    Explain a query from the user using an external agent process + MCP.
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

        console_whizz(f" * {random.choice(THINKING_MSGS)}...")
        print_agent(agent.display_name, agent.agent_bin)

        explanation = await agent.ask(why, port, tools=gateway.tools)

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


@command.register(
    gdb.COMMAND_USER,
    arg_parser=command_args.DashArgs(
        command_args.Option(
            long="agent",
            short="a",
            value=command_args.Choice(AgentRegistry.available_agents(), optional=True),
        ),
        allow_remainders=True,
    ),
)
def explain(udb: udb_base.Udb, args: Any) -> None:
    """
    Use AI to answer questions about the code.
    """
    why = args.untokenized_remainders or ""
    global agent
    if agent:
        # The agent cannot be switched within a session.
        if args.agent and args.agent != agent.name:
            raise Exception(
                f"Cannot switch agents within session - current agent is {agent.name!r}."
            )
    else:
        # If no agent was previously selected, choose one now.
        agent = AgentRegistry.select_agent(args.agent, log_level=LOG_LEVEL)

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
        unittest.mock.patch.object(udb, "_volatile_mode_explained", True),
    ):
        explanation = event_loop.run_until_complete(explain_query(agent, gateway, why))

        print_explanation(explanation)
