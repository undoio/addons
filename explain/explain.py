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
from typing import Any, Concatenate, Literal, ParamSpec, TypeAlias, TypeVar, cast

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
from .copilot_cli_agent import CopilotCLIAgent  # pylint: disable=unused-import
from .output_utils import console_whizz, print_agent, print_explanation, print_tool_call


# Prevent uvicorn trying to handle signals that already have special GDB handlers.
uvicorn.server.HANDLED_SIGNALS = ()  # type: ignore[assignment]

# Switch the debug level to get more context if the MCP server is misbehaving.
LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "CRITICAL"
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


def report(fn: Callable[P, T]) -> Callable[P, T | str]:
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
            results: T | str
            try:
                results = fn(*args, **kwargs)
            except Exception as e:
                results = str(e)
                raise e
            finally:
                if results is None:
                    results = ""

                tool_call.report_result(str(results).rstrip())

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


def get_context(fname: str, line: int) -> str:
    """
    Return formatted file context surrounding the current debug location.
    """
    try:
        lines = Path(fname).read_text(encoding="UTF-8").split("\n")
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
            source = get_context(sal.symtab.fullname(), sal.line)

        if source:
            context += "\nSource context:\n" + source
        else:
            context += "\nSource context unavailable."

        return out + context

    return cast(Callable[P, str], wrapped)


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


def cpp_get_uncaught_exceptions():
    """
    Return the current number of uncaught exceptions on the current thread.
    """
    return int(gdb.parse_and_eval("__cxa_get_globals()->uncaught_exceptions"))


def cpp_exception_state_present():
    """
    Do we have access to libstdc++ exception handling state in this program?
    """
    try:
        cpp_get_uncaught_exceptions()
        gdb.parse_and_eval("__cxa_throw")
    except gdb.error as e:
        e_str = str(e)
        if e_str.startswith("No symbol") and e_str.endswith("in current context."):
            return False
        raise
    else:
        return True


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
    @chain_of_thought
    def tool_last_value(self, expression: str) -> str:
        """
        Wind back time to the last time an expression was modified.

        This should NOT be used with function call expressions e.g. my_function(number) as
        it will be very slow.

        This should NOT be used for address-taken expressions, such as &variable_name, since this
        will be very slow and won't give a meaningful answer.

        This should NOT be used for debugger convenience variables (starting with a $), since this
        will be very slow.

        This should NOT be used on code (such as functions) unless it is being accessed via a
        non-const function pointer, since code will not change.

        Use expressions that are based solely on variables or memory locations. This may be used on
        both global and local variables to understand the flow of data in the program.  Where
        applicable it may be more efficient than stepping by source line.
        """
        # First, test whether the expression will make inferior calls and reject it if so - these
        # will be too slow.
        call_count = 0

        def _call_handler(_):
            nonlocal call_count
            call_count += 1

        with gdbutils.gdb_event_connected(gdb.events.inferior_call, _call_handler):
            gdb.parse_and_eval(expression)

        if call_count:
            return (
                f"Expression {expression} will cause function calls when evaluated. This tool "
                f"does not querying expressions that call functions as doing so would be very "
                f"slow. Consider querying for other data related to the value of this expression."
            )

        # Set up the reverse search itself.
        search = udb_last._LastSearch.from_expression(  # pylint: disable=protected-access
            self.udb, expression
        )

        result_backwards = search.search_change(udb_last.Direction.BACKWARD)

        if not result_backwards.found_something:
            return (
                f"Expression {expression} didn't change value before the current point "
                f"in time so there is no previous value to return."
            )

        # If we get here it did change value, so we'll position ourselves after the change.
        result_forwards = search.search_change(udb_last.Direction.FORWARD)
        assert result_forwards.found_something

        message = result_forwards.output

        if m := re.search(r".*Now = (.*)", message):
            # If we found a value change, extract just the "Now =" part of the message.
            message = f"has just been assigned value {m[1]}"

        # Put short messages on the same line as "Expression changed".
        separator = " " if len(message.splitlines()) == 1 else "\n"

        return f"Expression {expression} changed:{separator}{message}"

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
    def tool_reverse_finish(self, target_fn: str) -> None:
        """
        Run backwards to before the current function was called.

        This will traverse multiple levels of stack, if necessary, to get to the specified
        target. Use this when walking up a call stack to reduce the number of calls to this tool,
        which will improve performance.

        On success it will pop at least one stack frame, even in recursive calls. On failure it will
        return to the originally-selected stack frame.

        Params:
        target_fn: the function you want to reverse-finish back to. This must be present in
                   the current backtrace or the command will fail.
        """
        orig_frame = gdbutils.selected_frame()
        try:
            frame = orig_frame.older()
            while frame and frame.name() != target_fn:
                frame = frame.older()

            if not frame:
                raise Exception("No such frame in current backtrace.")

            # Finish out into the specified frame.
            frame.newer().select()
            self.udb.execution.reverse_finish(cmd="reverse-finish")

            assert gdbutils.selected_frame().name() == target_fn
        except:
            orig_frame.select()
            raise

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

            # Are C++ exceptions a potential consideration?
            #
            # If we cannot find the exception-handling state then either we're not in a C++ program
            # at all (in which case we don't handle exceptions) or we're lacking the relevant debug
            # information (in which case, for now, we'll just keep on trucking without it).
            cpp_exceptions = cpp_exception_state_present()

            # Get the number of uncaught exceptions before running the function.
            uncaught_exceptions_before = cpp_get_uncaught_exceptions() if cpp_exceptions else 0

            # We're at the start of the target function, now we need to get to the end.
            self.udb.execution.finish()

            if cpp_exceptions and cpp_get_uncaught_exceptions() > uncaught_exceptions_before:
                # There was an uncaught exception during this function's execution - we should
                # rewind to it and bail out.

                # Rewind to the throw.
                cxa_throw_bp = gdb.Breakpoint("__cxa_throw")
                self.udb.execution.reverse_cont()
                assert cxa_throw_bp.hit_count == 1, (
                    f"Expected to see cxa_throw_bp hit once while rewinding to an uncaught "
                    f"exception but instead saw {cxa_throw_bp.hit_count=}."
                )

                # Get back out of __cxa_throw and (hopefully) into the code that threw.
                self.udb.execution.reverse_finish(cmd="reverse-finish")
                # Bail out early here - the rest of the function wasn't run and there's no return to
                # handle.
                return (
                    f"Stopping early: An exception was thrown while attempting to step into "
                    f"{target_fn}"
                )

            return_value = gdb.parse_and_eval("$")
            return_value.fetch_lazy()

            # Step back into the end of the function.
            self.udb.execution.reverse_step(cmd="reverse-step")

            # Check that we got back into the function we intended.
            assert gdb.selected_frame().name() == target_fn

            func = gdb.selected_frame().function()
            if func and func.type.target() != gdb.TYPE_CODE_VOID:
                # Step further back to ensure we're at the return statement.
                with gdbutils.temporary_parameter("listsize", 1):
                    while "return" not in gdbutils.execute_to_string("list"):
                        self.udb.execution.reverse_next(cmd="reverse-next")

                # Check we're still in the function we intended.
                assert gdb.selected_frame().name() == target_fn

                # And that we've not gone back further than planned.
                assert (
                    target_start_bp.hit_count == 1
                ), "Unexpectedly reached the start of the target function."

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
    def tool_print(self, expressions: list[str]) -> str:
        """
        Get the value of one or more expressions at the current point in program history.

        This should NOT be used to retrieve the value of GDB value history
        variables such as $0, $1, $2, etc.

        Params:
        expressions -- the expressions to be evaluated.
        """

        def _safe_eval(e: str) -> str:
            try:
                v = gdb.parse_and_eval(e)
                return str(v)
            except Exception as e:
                return str(e)

        return "\n".join(f"{e} = {_safe_eval(e)}" for e in expressions)

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

        Use this to query interesting points in time that are already identified. These are
        returned in time order, with earlier results earlier in recorded history.

        A special "# Current time" value denotes the current point in program history.
        """
        bookmarks = list(self.udb.bookmarks.iter_bookmarks())
        bookmarks.append(("# Current time", self.udb.time.get()))

        # Sort by engine.Time value.
        return "\n".join((name for name, _ in sorted(bookmarks, key=lambda b: b[1])))

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
        gdbutils.temporary_parameter("backtrace past-main", True),
        udb.replay_standard_streams.temporary_set(False),
        gdbutils.breakpoints_suspended(),
        udb.signals_suspended(),
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
        gdbutils.temporary_parameter("confirm", False),
        gdbutils.temporary_parameter("backtrace past-main", True),
        udb.replay_standard_streams.temporary_set(False),
        gdbutils.breakpoints_suspended(),
        udb.signals_suspended(),
        unittest.mock.patch.object(udb, "_volatile_mode_explained", True),
    ):
        explanation = event_loop.run_until_complete(explain_query(agent, gateway, why))

        print_explanation(explanation)
