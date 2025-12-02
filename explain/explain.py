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
import socket
import unittest.mock
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Concatenate, Literal, ParamSpec, TypeAlias, TypeVar, cast, get_args

import gdb
import uvicorn.server
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import Prompt
from pydantic import BaseModel, ValidationError
from rich.padding import Padding
from src.udbpy import engine, event_info, ui
from src.udbpy.gdb_extensions import command, command_args, gdbio, gdbutils, udb_base, udb_last

# Agent modules are imported to trigger registration.
from .agents import AgentRegistry, BaseAgent
from .amp_agent import AmpAgent  # pylint: disable=unused-import
from .assets import FLOW_PROMPT, MCP_INSTRUCTIONS, SYSTEM_PROMPT, THINKING_MSGS
from .claude_agent import ClaudeAgent  # # pylint: disable=unused-import
from .codex_agent import CodexAgent  # pylint: disable=unused-import
from .copilot_cli_agent import CopilotCLIAgent  # pylint: disable=unused-import
from .output_utils import (
    ExplainPanel,
    console,
    console_whizz,
    print_agent,
    print_explanation,
    print_tool_call,
)


# Prevent uvicorn trying to handle signals that already have special GDB handlers.
uvicorn.server.HANDLED_SIGNALS = ()  # type: ignore[assignment]

# Switch the debug level to get more context if the MCP server is misbehaving.
LogLevel: TypeAlias = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _validate_log_level(level: str) -> LogLevel:
    """Validate and cast a string to a valid log level."""
    level = level.upper()
    valid_levels = get_args(LogLevel)
    if level not in valid_levels:
        raise ValueError(
            f"Invalid log level: {level!r}. Valid values are: {', '.join(valid_levels)}"
        )
    return cast(LogLevel, level)


LOG_LEVEL: LogLevel = "CRITICAL"  # pylint: disable=invalid-name,useless-suppression
# LOG_LEVEL="DEBUG"

# Override from environment variable if set
if _env_log_level := os.environ.get("EXPLAIN_LOG_LEVEL"):
    LOG_LEVEL = _validate_log_level(_env_log_level)


P = ParamSpec("P")
T = TypeVar("T")
UdbMcpGatewayAlias: TypeAlias = "UdbMcpGateway"


# Something in the webserver stack holds onto a reference to the event loop
# after shutting down. It's easier to just using the same event loop for each
# invocation.
event_loop = None


agent: BaseAgent | None = None
"""Agent instance for the current session."""


@contextlib.contextmanager
def temporary_gdb_settings(udb: udb_base.Udb) -> Iterator[None]:
    with (
        gdbutils.temporary_parameter("confirm", False),
        gdbutils.temporary_parameter("pagination", False),
        gdbutils.temporary_parameter("backtrace past-main", True),
        gdbutils.breakpoints_suspended(),
        udb.signals_suspended(),
        udb.replay_standard_streams.temporary_set(False),
        unittest.mock.patch.object(udb, "_volatile_mode_explained", True),
    ):
        yield


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


def cpp_get_uncaught_exceptions() -> int:
    """
    Return the current number of uncaught exceptions on the current thread.
    """
    # Get a pointer to the base of the C++ runtime's per-thread globals.
    cxa_globals = gdb.parse_and_eval("(char *)__cxa_get_globals()")

    # The globals structure contains a pointer, followed by an unsigned int that stores the current
    # count of uncaught exceptions.
    #
    # See https://itanium-cxx-abi.github.io/cxx-abi/abi-eh.html#cxx-data for more details.
    #
    # Mark saw the naming for the "uncaughtExceptions" field appear to vary but has not been able to
    # reproduce this. However, the names are not always available at all if debug symbols are not
    # present.
    #
    # Since this is part of the ABI we can calculate the address to look up the current uncaught
    # exception count, rather than rely on symbols.

    void_ptr_type = gdb.lookup_type("void").pointer()
    unsigned_int_type = gdb.lookup_type("unsigned int")

    # The globals structure contains pointer followed by the unsigned int we are looking for. We can
    # calculate a pointer to that unsigned int member.
    uncaught_ptr = (cxa_globals + void_ptr_type.sizeof).cast(unsigned_int_type.pointer())

    return int(uncaught_ptr.dereference())


def cpp_exception_state_present() -> bool:
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


def gtest_libraries_present() -> bool:
    """
    Is this program linked against gtest libraries?
    """
    obj_paths = (Path(o.filename) for o in gdb.objfiles() if o.filename is not None)
    return any(o.name.startswith("libgtest") for o in obj_paths)


class GTestNotAvailable(Exception):
    """
    Raised by GTest-specific tools if the Google Test libraries are not present.
    """

    def __init__(self):
        super().__init__("Tool unavailable: This program was not run with gtest.")


class GTestAnnotationsNotAvailable(Exception):
    """
    Raised by GTest-specific tools if our Google Test annotations are not found.
    """

    def __init__(self):
        super().__init__(
            "Tool unavailable: Did not find gtest annotations, which are required to navigate "
            "Google Test recordings. Maybe the program was built without the "
            "Undo's `undo_gtest_annotation.h` addon?"
        )


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

    def _reverse_into_target_function(self, target_fn: str) -> str:
        """
        Reverse from the current line into the previous call of the target function in this thread.

        This is to be used in the implementation of other tools that need to step into a function.

        Params:
        target_fn: the function to reverse into.

        Returns: A string describing either the return value or the reason for an early stop.
        """
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
            print(f"_reverse_into_target_function internal messages:\n{collector.output}")

        return f"{target_fn} return value: {return_value}"

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

        Returns: A string describing either the return value or the reason for an early stop.
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

        return self._reverse_into_target_function(target_fn)

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
    def tool_ubookmark(self, name: str) -> None:
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
    def tool_ugo_bookmark(self, name: str) -> None:
        """
        Travels to the time of a named bookmark that was previously set.

        You can only use this for bookmarks that you have previously set using
        `ubookmark` or that appear in the output of `info_bookmarks`.

        Use this to investigate further from an interesting point in time.
        """
        self.udb.bookmarks.goto(name)

    @report
    @chain_of_thought
    def tool_gtest_get_tests(self) -> list[tuple[str, str]]:
        """
        Retrieve a list of GTest tests captured in this recording, along with their results.

        Full test names are returned in the form:

           <test suite name>.<test name>/run<run number>

        Each instance of a test is assigned a unique run number. Run numbers don't have meaning
        beyond being a unique suffix.

        Returns a list of (<full test name>, <result>) tuples.
        """
        if not gtest_libraries_present():
            raise GTestNotAvailable()

        results = list(self.udb.annotations.get("", "u-test-result"))
        if not results:
            raise GTestAnnotationsNotAvailable()

        return [(r.name, r.get_content_as_printable_text()) for r in results]

    @report
    @source_context
    @chain_of_thought
    def tool_gtest_goto_test(self, name: str) -> str:
        """
        Move to the end of the specified Gtest test case.
        """
        if not gtest_libraries_present():
            raise GTestNotAvailable()

        if not list(self.udb.annotations.get("", "u-test-result")):
            raise GTestAnnotationsNotAvailable()

        results = list(self.udb.annotations.get(name, "u-test-result"))
        if len(results) != 1:
            raise Exception("Must specify a unique, existing test identifier.")

        annotation = results[0]
        self.udb.time.goto(annotation.bbcount)

        test_name, _ = annotation.name.split("/run")
        target_fn = test_name.replace(".", "_") + "_Test::TestBody"

        return self._reverse_into_target_function(target_fn)


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
    with temporary_gdb_settings(udb):
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
    with temporary_gdb_settings(udb):
        explanation = event_loop.run_until_complete(explain_query(agent, gateway, why))

        print_explanation(explanation)


# =============================================================================
# Flow Command - Value Origin Tracking
# =============================================================================


class FlowCheckpoint(BaseModel):
    """Checkpoint data for restoring flow position."""

    bbcount: int
    pc: int | None
    function: str
    expression: str
    value: str


class FlowLocation(BaseModel):
    """Location information for a flow step."""

    file: str
    line: int
    function: str
    source_line: str


class FlowAnalysis(BaseModel):
    """Analysis of the current flow step."""

    description: str
    source_binary_match: bool
    summary: str | None = None  # Short one-line summary (10-15 words max)


class FlowNextStep(BaseModel):
    """A suggested next step in flow tracking."""

    id: int
    action: Literal[
        "last_value", "reverse_step_into_current_line", "reverse_finish", "reverse_next"
    ]
    reasoning: str
    priority: Literal["high", "medium", "low"]
    # Optional fields depending on action type
    expression_to_track: str | None = None
    target_fn: str | None = None


class FlowResponse(BaseModel):
    """Complete response from LLM flow analysis."""

    checkpoint: FlowCheckpoint
    location: FlowLocation
    analysis: FlowAnalysis
    next_steps: list[FlowNextStep]
    should_continue: bool
    stopping_reason: (
        Literal[
            "origin_found",
            "step_limit_reached",
            "ambiguous_flow",
            "optimized_away",
            "external_input",
            "cannot_navigate",
            "llm_error",
        ]
        | None
    )


def _gather_flow_context(udb: udb_base.Udb, expression: str) -> dict:
    """
    Gather complete debugging context at current location.

    Returns dict with tracking info, location, source, disassembly, registers, locals, backtrace.
    """
    # Get current position
    bookmarked = udb.time.get_bookmarked()
    frame = gdb.selected_frame()
    sal = frame.find_sal()

    # Safe expression evaluation - check for inferior calls
    value = "<unknown>"
    call_count = 0

    def _call_handler(_):
        nonlocal call_count
        call_count += 1

    try:
        with gdbutils.gdb_event_connected(gdb.events.inferior_call, _call_handler):
            result = gdb.parse_and_eval(expression)
        if call_count:
            value = "<requires function call>"
        else:
            result.fetch_lazy()
            value = str(result)
    except gdb.error as e:
        value = f"<error: {e}>"

    # Build context
    context: dict[str, Any] = {
        "tracking": {
            "expression": expression,
            "current_value": value,
        },
        "location": {
            "file": sal.symtab.fullname() if sal and sal.symtab else "<unknown>",
            "line": sal.line if sal else 0,
            "function": frame.name() or "<unknown>",
            "bbcount": bookmarked.time.bbcount,
            "pc": bookmarked.time.pc,
        },
        "source": "",
        "disassembly": "",
        "registers": "",
        "locals": "",
        "backtrace": "",
    }

    # Get source context
    if sal and sal.symtab:
        context["source"] = get_context(sal.symtab.fullname(), sal.line)

    # Get disassembly
    try:
        context["disassembly"] = gdbutils.execute_to_string("disassemble")
    except gdb.error:
        context["disassembly"] = "<unavailable>"

    # Get registers
    try:
        context["registers"] = gdbutils.execute_to_string("info registers")
    except gdb.error:
        context["registers"] = "<unavailable>"

    # Get locals
    try:
        context["locals"] = gdbutils.execute_to_string("info locals")
    except gdb.error:
        context["locals"] = "<unavailable>"

    # Get backtrace (limited to 5 frames)
    try:
        context["backtrace"] = gdbutils.execute_to_string("bt 5")
    except gdb.error:
        context["backtrace"] = "<unavailable>"

    return context


def _extract_json_from_response(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to extract from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    # Otherwise return the text as-is (hopefully it's raw JSON)
    return text.strip()


def _build_flow_question(context: dict, history: list[FlowResponse]) -> str:
    """Build the complete question for flow analysis, including instructions and context."""
    # Build history text
    history_text = ""
    if history:
        history_text = "\n\n## Previous Steps\n\n"
        for i, step in enumerate(history):
            history_text += f"### Step {i + 1}\n"
            loc = step.location
            history_text += f"- Location: `{loc.file}:{loc.line}` in `{loc.function}()`\n"
            history_text += f"- Source: `{step.location.source_line}`\n"
            history_text += f"- Analysis: {step.analysis.description}\n\n"

    # Include FLOW_PROMPT in the question since agents have their own system prompts
    return f"""# Flow Analysis Task

{FLOW_PROMPT}

---

# Current Analysis Request

Analyze this flow tracking state and return a JSON response.

## Current Context

### Tracking
- Expression: `{context["tracking"]["expression"]}`
- Current value: `{context["tracking"]["current_value"]}`

### Location
- File: `{context["location"]["file"]}`
- Line: {context["location"]["line"]}
- Function: `{context["location"]["function"]}`
- BBCount: {context["location"]["bbcount"]}
- PC: {context["location"]["pc"]}

### Source
```
{context["source"] or "<source unavailable>"}
```

### Disassembly
```
{context["disassembly"]}
```

### Registers
```
{context["registers"]}
```

### Local Variables
```
{context["locals"]}
```

### Backtrace
```
{context["backtrace"]}
```
{history_text}
**IMPORTANT**: Return ONLY a JSON object following the schema above. Do not use any tools.
Do not wrap in markdown code blocks. Just return the raw JSON."""


async def _ask_agent_flow(flow_agent: BaseAgent, gateway: UdbMcpGateway, question: str) -> str:
    """
    Ask the agent to analyze flow and return the response.

    Similar to explain_query but for flow analysis.
    """
    sock = None
    server = None
    mcp_task = None
    try:
        sock = socket.create_server(("localhost", 0))
        _, port = sock.getsockname()

        # Set up a temporary MCP server (required by agent infrastructure)
        starlette_app = gateway.mcp.sse_app()
        config = uvicorn.Config(starlette_app, log_level=LOG_LEVEL.lower())
        server = uvicorn.Server(config)
        mcp_task = asyncio.create_task(server.serve(sockets=[sock]))

        # Ask the agent - pass tools but instruct LLM not to use them in the question
        response = await flow_agent.ask(question, port, tools=gateway.tools)

    finally:
        # Shut down the server
        if server:
            server.should_exit = True
            await server.shutdown()
        if mcp_task:
            await mcp_task
        if sock:
            sock.close()

    return response


def _call_llm_analyze_flow(
    flow_agent: BaseAgent,
    gateway: UdbMcpGateway,
    context: dict,
    history: list[FlowResponse],
    debug: bool = False,
) -> FlowResponse:
    """
    Call LLM to analyze current flow step using the agent infrastructure.

    Returns parsed FlowResponse or raises on failure.
    """
    global event_loop
    if not event_loop:
        event_loop = asyncio.new_event_loop()

    question = _build_flow_question(context, history)

    # Try up to 2 times (initial + 1 retry)
    last_error = None
    raw_response = ""

    for attempt in range(2):
        try:
            raw_response = event_loop.run_until_complete(
                _ask_agent_flow(flow_agent, gateway, question)
            )

            if debug:
                print(f"\n[DEBUG] Raw LLM response (attempt {attempt + 1}):")
                print(raw_response)
                print()

            # Extract and parse JSON
            json_text = _extract_json_from_response(raw_response)
            data = json.loads(json_text)
            response = FlowResponse.model_validate(data)
            return response

        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            if not attempt:
                # Retry once
                continue
            # Second failure - give up
            raise RuntimeError(
                f"LLM returned invalid JSON after retry: {e}\n\nRaw response:\n{raw_response}"
            ) from e

    # Should not reach here, but just in case
    raise RuntimeError(f"Failed to get valid LLM response: {last_error}")


def _display_flow_step(step_num: int, response: FlowResponse, source_context: str) -> None:
    """Display current flow step to user with rich markdown formatting."""
    from rich.markdown import Markdown
    from rich.syntax import Syntax

    loc = response.location
    analysis = response.analysis
    checkpoint = response.checkpoint

    # Build markdown content
    md_parts = []

    # Header with location and time
    pc_str = f"0x{checkpoint.pc:x}" if checkpoint.pc else "?"
    md_parts.append(
        f"**Step {step_num}**: `{loc.function}()` at `{Path(loc.file).name}:{loc.line}` "
        f"(time {checkpoint.bbcount}:{pc_str})"
    )
    md_parts.append("")

    # Tracking info
    md_parts.append(f"**Tracking**: `{checkpoint.expression}` = `{checkpoint.value}`")
    md_parts.append("")

    # Analysis
    md_parts.append(f"**Analysis**: {analysis.description}")

    if not analysis.source_binary_match:
        md_parts.append("")
        md_parts.append("⚠️ *Source code may not match binary (possible optimization)*")

    # Next steps
    if response.next_steps:
        md_parts.append("")
        md_parts.append("**Next steps**:")
        for step in response.next_steps:
            priority_marker = {"high": "HIGH", "medium": "MED", "low": "LOW"}[step.priority]
            if step.action == "last_value":
                action_desc = f"Track `{step.expression_to_track}`"
            elif step.action == "reverse_step_into_current_line":
                action_desc = f"Step into `{step.target_fn}()`"
            elif step.action == "reverse_finish":
                action_desc = f"Return to `{step.target_fn}()`"
            elif step.action == "reverse_next":
                action_desc = "Step to previous line"
            else:
                action_desc = step.action
            md_parts.append(f"- **[{step.id}]** {priority_marker}: {action_desc}")

    # Stopping reason
    if not response.should_continue:
        reason_msgs = {
            "origin_found": "✅ Found the origin of this value",
            "step_limit_reached": "⏹️ Reached maximum tracking steps",
            "ambiguous_flow": "❓ Flow is too ambiguous to track automatically",
            "optimized_away": "⚠️ Value was optimized away by compiler",
            "external_input": "📥 Value comes from external input",
            "cannot_navigate": "🚫 Cannot navigate to the required location",
            "llm_error": "❌ Error analyzing the flow",
        }
        reason = response.stopping_reason or "unknown"
        md_parts.append("")
        md_parts.append(f"**Stopped**: {reason_msgs.get(reason, reason)}")

    # Render with rich
    md_content = "\n".join(md_parts)
    console.print(ExplainPanel(Markdown(md_content), title="Flow"))

    # Show source context if available
    if source_context and source_context.strip():
        # Source context is already formatted with line numbers and arrows
        console.print(Syntax(source_context, "c", theme="monokai", line_numbers=False))


def _execute_flow_step(gateway: UdbMcpGateway, step: FlowNextStep) -> str | None:
    """
    Execute a navigation step based on action type.

    Returns the new expression to track (if changed), or None.
    """
    hypothesis = step.reasoning

    if step.action == "last_value":
        if step.expression_to_track is None:
            raise ValueError("last_value action requires expression_to_track")
        gateway.tool_last_value(hypothesis, step.expression_to_track)
        return step.expression_to_track

    elif step.action == "reverse_step_into_current_line":
        if step.target_fn is None:
            raise ValueError("reverse_step_into_current_line action requires target_fn")
        gateway.tool_reverse_step_into_current_line(hypothesis, step.target_fn)
        # After stepping into function, we're tracking the return value
        # The LLM will determine what to track next based on context
        return None

    elif step.action == "reverse_finish":
        if step.target_fn is None:
            raise ValueError("reverse_finish action requires target_fn")
        gateway.tool_reverse_finish(hypothesis, step.target_fn)
        return None

    elif step.action == "reverse_next":
        gateway.tool_reverse_next(hypothesis)
        return None

    else:
        raise ValueError(f"Unknown action: {step.action}")


def _prompt_user_choice(next_steps: list[FlowNextStep]) -> FlowNextStep | None:
    """
    Present next steps to user and get their choice.

    Returns the chosen step, or None to stop.
    """
    while True:
        try:
            choice_str = ui.get_user_input(prompt=f"Your choice [1-{len(next_steps)}, q to quit]: ")
        except EOFError:
            return None

        choice_str = choice_str.strip().lower()
        if choice_str == "q":
            return None

        try:
            choice = int(choice_str)
            if 1 <= choice <= len(next_steps):
                return next_steps[choice - 1]
            print(f"Please enter a number between 1 and {len(next_steps)}")
        except ValueError:
            print("Please enter a valid number or 'q' to quit")


def _display_flow_summary(
    history: list[tuple[FlowResponse, FlowNextStep | None]],
    final: tuple[FlowResponse, FlowNextStep | None] | None,
    context_lines: int = 2,
) -> None:
    """Display a compact summary of the flow tracking session."""
    # Include final response if not already in history
    all_steps = list(history)
    if final:
        final_resp, _ = final
        # Check if final is already in history
        if not history or history[-1][0] != final_resp:
            all_steps.append(final)

    if not all_steps:
        console.print("[dim]No flow steps to summarize.[/dim]")
        return

    console.print()
    console_whizz(" * Flow Summary")

    # Print each step with source context
    for i, (step, _) in enumerate(all_steps):
        loc = step.location
        cp = step.checkpoint

        # Find the actual line number by searching for source_line in the file
        # (the debugger position may be off by one or more lines)
        actual_line = loc.line
        file_lines: list[str] | None = None
        try:
            source_path = Path(loc.file)
            if source_path.exists() and loc.source_line:
                file_lines = source_path.read_text().splitlines()
                source_stripped = loc.source_line.strip()
                search_range = range(max(0, loc.line - 5), min(len(file_lines), loc.line + 5))
                for ln in search_range:
                    if file_lines[ln].strip() == source_stripped:
                        actual_line = ln + 1  # 1-indexed
                        break
        except Exception:
            pass

        # Display header with the actual source line number
        loc_str = f"{Path(loc.file).name}:{actual_line}"
        pc_str = f"0x{cp.pc:x}" if cp.pc else "?"
        time_str = f"{cp.bbcount}:{pc_str}"

        console.print(
            f"\n  [dim][{i + 1}][/dim] [cyan]{loc_str}[/cyan] [dim]@ {time_str}[/dim]  "
            f"[green]{cp.expression}[/green] = {cp.value}"
        )

        # Show LLM-generated summary as markdown
        if step.analysis.summary:
            from rich.markdown import Markdown

            console.print(Padding(Markdown(step.analysis.summary), (0, 6)))

        # Show source context (N lines before, current, N lines after)
        try:
            if file_lines is not None and context_lines >= 0:
                start = max(0, actual_line - 1 - context_lines)  # 0-indexed
                end = min(len(file_lines), actual_line + context_lines)

                # Strip leading blank lines (but keep actual_line)
                actual_idx = actual_line - 1  # 0-indexed
                while start < actual_idx and not file_lines[start].strip():
                    start += 1
                # Strip trailing blank lines (but keep actual_line)
                while end > actual_idx + 1 and not file_lines[end - 1].strip():
                    end -= 1

                source_context = file_lines[start:end]

                # Find common indentation to de-indent
                non_empty = [ln for ln in source_context if ln.strip()]
                if non_empty:
                    min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
                else:
                    min_indent = 0

                # Display with arrow prefix (aligned with explanation indent)
                for line_num in range(start, end):
                    line_content = file_lines[line_num]
                    # De-indent
                    if len(line_content) >= min_indent:
                        line_content = line_content[min_indent:]
                    display_num = line_num + 1  # 1-indexed

                    if display_num == actual_line:
                        console.print(f"      [bold]->[/bold] [white]{line_content}[/white]")
                    else:
                        console.print(f"         [dim]{line_content}[/dim]")
            elif loc.source_line:
                # No file access, just show the source line
                console.print(f"      [bold]->[/bold] [white]{loc.source_line.strip()}[/white]")
        except Exception:
            if loc.source_line:
                console.print(f"      [bold]->[/bold] [white]{loc.source_line.strip()}[/white]")

    # Final conclusion
    final_response = final[0] if final else None
    if final_response and not final_response.should_continue and final_response.stopping_reason:
        from rich.markdown import Markdown

        reason_msgs = {
            "origin_found": "✅ Origin found",
            "optimized_away": "⚠️ Optimized away",
            "external_input": "📥 External input",
            "ambiguous_flow": "❓ Ambiguous",
        }
        msg = reason_msgs.get(final_response.stopping_reason, final_response.stopping_reason)
        console.print(f"\n[bold]{msg}[/bold]:")
        console.print(Markdown(final_response.analysis.description))
    console.print()


@command.register(
    gdb.COMMAND_USER,
    arg_parser=command_args.DashArgs(
        command_args.Option(
            long="agent",
            short="a",
            value=command_args.Choice(AgentRegistry.available_agents(), optional=True),
        ),
        command_args.Option(
            long="debug",
            short="d",
        ),
        command_args.Option(
            long="max-steps",
            short="m",
            value=command_args.Integer(purpose="max steps", default=20, minimum=1),
        ),
        command_args.Option(
            long="context",
            short="c",
            value=command_args.Integer(purpose="context lines", default=2, minimum=0),
        ),
        allow_remainders=True,
    ),
)
def flow(udb: udb_base.Udb, args: Any) -> None:
    """
    Track the flow of a value backward through program execution.

    This command uses AI to analyze how a variable or expression got its current value,
    stepping backward through time to trace its origin.

    Usage: flow [--agent NAME] [--debug] [--max-steps N] [--context N] <expression>

    Options:
      --agent, -a     AI agent to use (default: auto-detect)
      --debug, -d     Show raw LLM JSON responses for debugging
      --max-steps, -m Maximum number of tracking steps (default: 20)
      --context, -c   Lines of source context in summary (default: 2)
    """
    expression = args.untokenized_remainders
    if not expression:
        print("Usage: flow <expression>")
        print("Example: flow my_variable")
        return

    debug = args.debug
    max_steps = args.max_steps

    # Select or reuse agent (shared with explain command)
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

    gateway = UdbMcpGateway(udb)
    # History stores (response, chosen_step) tuples; chosen_step is None for final step
    history: list[tuple[FlowResponse, FlowNextStep | None]] = []
    step_num = 0
    last_response: FlowResponse | None = None

    console_whizz(f" * Tracking flow of `{expression}`...")

    with temporary_gdb_settings(udb):
        while step_num < max_steps:
            # Gather complete context
            try:
                context = _gather_flow_context(udb, expression)
            except Exception as e:
                print(f"Error gathering context: {e}")
                break

            # Call LLM to analyze (extract just responses from history tuples)
            try:
                history_responses = [resp for resp, _ in history]
                last_response = _call_llm_analyze_flow(
                    agent, gateway, context, history_responses, debug=debug
                )
            except RuntimeError as e:
                print(f"Error from LLM: {e}")
                break

            # Display to user
            _display_flow_step(step_num + 1, last_response, context.get("source", ""))

            # Check if should stop
            if not last_response.should_continue:
                break

            # Handle next steps
            next_steps = last_response.next_steps

            if not next_steps:
                print("No next steps available. Stopping.\n")
                break

            elif len(next_steps) == 1:
                # Linear flow - auto-continue
                chosen = next_steps[0]
                console.print(f"[dim]→ Auto-selecting [{chosen.id}][/dim]\n")

            else:
                # Fork - ask user
                chosen_step = _prompt_user_choice(next_steps)
                if chosen_step is None:
                    print("Stopping flow tracking.\n")
                    break
                chosen = chosen_step
                print()

            # Execute chosen step
            try:
                new_expression = _execute_flow_step(gateway, chosen)
                if new_expression:
                    expression = new_expression
            except Exception as e:
                print(f"Navigation failed: {e}")
                print("Stopping flow tracking.\n")
                break

            # Update history with chosen step
            history.append((last_response, chosen))
            step_num += 1

        if step_num >= max_steps:
            console.print(f"[yellow]Stopped: Reached maximum tracking steps ({max_steps})[/yellow]")

    # Print summary (pass final response with None for chosen step)
    _display_flow_summary(history, (last_response, None) if last_response else None, args.context)


command.register_prefix(
    "uinternal mcp",
    gdb.COMMAND_NONE,
    """
    Internal commands for managing MCP integration.
    """,
)


@command.register(
    gdb.COMMAND_USER,
    arg_parser=command_args.Multiple(
        command_args.String(purpose="tool name"),
        command_args.String(purpose="start delimiter"),
        command_args.String(purpose="end delimiter"),
        command_args.Filename(purpose="recording"),
        command_args.String(purpose="tool arguments as json"),
    ),
)
def uinternal__mcp__invoke_tool(
    udb: udb_base.Udb,
    tool_name: str,
    start_delim: str,
    end_delim: str,
    recording: Path,
    tool_args_json: str,
) -> None:
    """
    Invoke a tool directly on a recording
    """
    gateway = UdbMcpGateway(udb)
    try:
        fn = getattr(gateway, f"tool_{tool_name}")
    except AttributeError:
        raise RuntimeError(f"No such tool {tool_name!r}; valid tools: {', '.join(gateway.tools)}")

    already_loaded_recording = (
        udb.inferiors.selected._recording_path  # pylint: disable=protected-access
    )
    if (
        already_loaded_recording is None
        or already_loaded_recording.resolve() != recording.resolve()
    ):
        udb.recording.load(recording, will_goto_end=True)
        udb.time.goto_end_on_load()

    tool_kwargs = json.loads(tool_args_json)
    assert isinstance(tool_kwargs, dict), "Tool arguments must be a JSON object"
    with temporary_gdb_settings(udb):
        result = fn(**tool_kwargs)
    print(f"{start_delim}\n{json.dumps(result)}\n{end_delim}")


@command.register(gdb.COMMAND_USER, arg_parser=command_args.String(purpose="token"))
def uinternal__mcp__self_check(udb: udb_base.Udb, token: str) -> None:
    """
    Echo back a token to check the extension is running correctly.
    """
    print(f"Self check token: {token}")
