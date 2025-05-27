import asyncio
import contextlib
import functools
import inspect
import json
import os
import random
import signal
import socket
import tempfile
import textwrap
import time

from pathlib import Path

import gdb
import pygments
import pygments.formatters

from mcp.server.fastmcp import FastMCP

from src.udbpy.fileutil import mkstemp
from src.udbpy.gdb_extensions import command, command_args, gdbio, gdbutils, udb_base, udb_last
from src.udbpy.termstyles import ansi_format, Color, Intensity


import uvicorn.server
# Prevent uvicorn trying to handle signals that already have special GDB handlers.
uvicorn.server.HANDLED_SIGNALS = ()

# Switch the debug level to get more context if the MCP server is misbehaving.
LOG_LEVEL="CRITICAL"
#LOG_LEVEL="DEBUG"


EXTENSION_PATH = Path(__file__).parent
"""Directory containing this extension module."""

MCP_INSTRUCTIONS = open(EXTENSION_PATH / "instructions.md").read()
"""Top-level instructions for the MCP server."""

SYSTEM_PROMPT = open(EXTENSION_PATH / "system_prompt.md").read()
"""System prompt to supply to Claude on every invocation."""

THINKING_MSGS = [l.rstrip() for l in open(EXTENSION_PATH / "thinking.txt").readlines()]
"""Messages to display whilst the system is thinking."""


def console_whizz(msg, end=""):
    """
    Animated console display for major headings.
    """
    for c in msg:
        print(ansi_format(c, foreground=Color.GREEN, intensity=Intensity.BOLD), end="", flush=True)
        time.sleep(0.01)
    print(end=end)


def print_report_field(label, msg):
    """
    Formatted field label for reporting command results.
    """
    label_fmt = ansi_format(f"{label +':':10s}", foreground=Color.WHITE, intensity=Intensity.BOLD)
    print(f" | {label_fmt} {msg}")


def report(fn):
    """
    Wrap a tool to report on the current thinking state (if appropriate) and result.
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
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
            if len(results.splitlines()) == 1:
                result_text = results
            else:
                result_text = "\n" + textwrap.indent(results, "   $  ", predicate=lambda _: True)

            print_report_field("Result", result_text)
            print(" |---")
            return results

    return wrapped


def collect_output(fn):
    """
    Collect GDB's output during the execution of the wrapped function.

    Used to pass back interactive output directly to the LLM.
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with gdbio.CollectOutput() as collector:
            fn(*args, **kwargs)

        return collector.output

    return wrapped


SOURCE_CONTEXT_LINES = 5
"""The maximum size of source context to show either side of the current position."""


def get_context(fname, line):
    """
    Return formatted file context surrounding the current debug location.
    """
    lines = open(fname).readlines()

    start_line = max(0, line - SOURCE_CONTEXT_LINES)
    end_line = min(len(lines), line + SOURCE_CONTEXT_LINES)

    formatted_lines = list(f"{i + 1: 5d} {lines[i].rstrip()}" for i in range(start_line, end_line))
    formatted_lines.insert(line - 1 - start_line, "   ->")

    return "\n".join(formatted_lines)


def source_context(fn):
    """
    Add source location context to the result of a wrapped function.

    This informs the LLM of the current source context when the command returns, useful when a
    command moves through debug history.
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        out = fn(*args, **kwargs)

        frame = gdb.selected_frame()
        sal = frame.find_sal()

        context = f"\nFunction: {frame.name()}\n"

        if sal and sal.symtab:
            context += "\nSource context:\n" + get_context(sal.symtab.filename, sal.line)
        else:
            context += "\nSource context unavailable."
        return out + context

    return wrapped


def chain_of_thought(fn):
    """
    Add chain-of-thought parameters and documentation to the wrapped function.

    This requires the LLM to explain its reasoning as it goes along, leading to better or more
    understandable results.
    """
    @functools.wraps(fn)
    def wrapped(self, hypothesis: str, *args, **kwargs):
        return fn(self, *args, **kwargs)

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    params += [inspect.Parameter(param, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
               for param in ("hypothesis",)]
        
    wrapped.__signature__ = sig.replace(parameters=params)

    wrapped.__doc__ += """
        Additional parameters:
        hypothesis -- describe the hypothesis you are currently investigating.
    """

    return wrapped


class UdbMcpGateway:
    def __init__(self, udb: udb_base.Udb):
        self.udb = udb
        self.mcp = FastMCP("UDB_Server", instructions=MCP_INSTRUCTIONS, log_level=LOG_LEVEL)
        self.tools = []
        self._register_tools()


    def _register_tools(self) -> None:
        for name, fn in inspect.getmembers(self, inspect.ismethod):
            if not name.startswith("tool_"):
                continue
            name = name.removeprefix("tool_")
            self.tools.append(name)
            self.mcp.add_tool(fn=fn, name=name, description=fn.__doc__)


    @report
    @chain_of_thought
    def tool_get_time(self) -> str:
        """
        Get the current point in recorded history.
        """
        return str(self.udb.time.get())


    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_ugo_end(self) -> str:
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
    def tool_last_value(self, expression: str) -> str:
        """
        Wind back time to the last time an expression was modified.

        This should NOT be used with function call expressions e.g. my_function(number) as
        it will be very slow.

        Use expressions that are based solely on variables or memory locations.
        """
        self.udb.last.execute_command(
            expression, direction=udb_last.Direction.BACKWARD, is_repeated=False
        )


    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_next(self) -> str:
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
    def tool_reverse_finish(self) -> str:
        """
        Run backwards to before the current function was called.
        """
        self.udb.execution.reverse_finish(cmd="reverse-finish")

    @report
    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_step(self, intended_function: str) -> str:
        """
        Step into the return path of a function on an earlier line of source code.

        `reverse_step` will step backwards into a function on the previous line.
        You may need to issue `reverse_step` more than once to reach the `return` statement.

        It CANNOT be used to step into functions on the current line.
        ```
        Example: investigate the return path of called_function()
        
        Source context:
             8       int my_value = called_function();
            ->
             9       a = a + b;
        
        UDB:reverse_step (repeat, if necessary)
        
             2      int called_function(void)
             3      {
            ->
             4          return 7;
             5      }
             6
        ```
        
        ```
        Example: investigate the return path of function_one()
        
        Source context:
           12  int main(void)
           13  {
           14      function_one(7);
           ->
           15      function_two();
           16  }
        
        UDB:reverse_step
        
            4  void function_one(int arg)
            5  {
            6      printf("Argument was: %d\n", arg);
           ->
            7  }
            8
        ```

        Params:
        intended_function: the function you want to step into
        """
        # Note that, even with the prompting above, Claude will often fail to
        # use `reverse-step` correctly, instead applying it when the function
        # it wants to step into is on the current line.
        self.udb.execution.reverse_step(cmd="reverse-step")


    @report
    @chain_of_thought
    def tool_backtrace(self) -> str:
        """
        Get a backtrace of the code at the current point in time.
        """
        return gdbutils.execute_to_string("backtrace")


    @report
    @chain_of_thought
    def tool_get_value(self, expression: str) -> str:
        """
        Get the value of an expression.

        Params:
        expression -- the expression to be evaluated.
        """
        return str(gdb.parse_and_eval(expression))


command.register_prefix(
    "uexperimental mcp",
    gdb.COMMAND_NONE,
    """
    Experimental commands for managing MCP integration.
    """,
)


@command.register(gdb.COMMAND_USER)
def uexperimental__mcp__serve(udb: udb_base.Udb) -> None:
    """
    Start an MCP server for this UDB instance.
    """
    gateway = UdbMcpGateway(udb)
    gateway.mcp.run(transport="sse")


async def _ask_claude(why: str, port: int, tools: list[str]):
    """
    Pose a question to an external `claude` program, supplying access to a UDB MCP server.
    """
    if LOG_LEVEL == "debug":
        print(f"Connecting Claude to MCP server on port {port}")
    else:
        console_whizz(f" * {random.choice(THINKING_MSGS)}...", end="\n")
        print(" |---")

    mcp_config = {
        "mcpServers" : {
            "UDB_Server": {
                "type": "sse",
                "url": f"http://localhost:{port}/sse"
            }
        }
    }
    mcp_config_fd, mcp_config_path = mkstemp(prefix="mcp_config", suffix=".json")
    with contextlib.closing(os.fdopen(mcp_config_fd, "w")) as mcp_config_file:
        json.dump(mcp_config, mcp_config_file)

    allowed_tools = ",".join(f"mcp__UDB_Server__{t}" for t in tools)

    # If we're gathering debug logs then get as much feedback from Claude as possible.
    debug_flags = ["--verbose", "-d"] if LOG_LEVEL == "DEBUG" else []

    stdout = ""
    try:
        claude = await asyncio.create_subprocess_exec("claude",
                                                      *debug_flags,
                                                      "--model", "opus",
                                                      "--mcp-config", mcp_config_path,
                                                      "--allowedTools", allowed_tools,
                                                      "-p", why,
                                                      "--system-prompt", SYSTEM_PROMPT,
                                                      stdout=asyncio.subprocess.PIPE,
                                                      stderr=asyncio.subprocess.PIPE)

        stdout, _ = await claude.communicate()
    finally:
        # Make sure Claude is properly cleaned up if we exited early.
        if claude.returncode is None:
            claude.terminate()
            await claude.wait()

    return stdout


async def _explain(gateway: UdbMcpGateway, why: str) -> str:
    """
    Explain a query from the user using an external `claude` process + MCP.
    """
    try:
        sock = socket.create_server(("localhost", 0))
        _, port = sock.getsockname()

        # Set up a temporary MCP server for this UDB session.
        starlette_app = gateway.mcp.sse_app()
        config = uvicorn.Config(starlette_app, log_level=LOG_LEVEL.lower())
        server = uvicorn.Server(config)
        mcp_task = asyncio.create_task(server.serve(sockets=[sock]))

        # Ask Claude the question.
        explanation = await _ask_claude(why, port, tools=gateway.tools)

    finally:
        # Shut down the server once we have an explanation.
        server.should_exit = True
        await server.shutdown()
        await mcp_task
        sock.close()

    return explanation


# Something in the webserver stack holds onto a reference to the event loop
# after shutting down. It's easier to just using the same event loop for each
# invocation.
event_loop = asyncio.new_event_loop()

@command.register(gdb.COMMAND_USER, arg_parser=command_args.Untokenized())
def explain(udb: udb_base.Udb, why: str) -> None:
    """
    Use AI to answer questions about the code.
    """
    gateway = UdbMcpGateway(udb)

    global event_loop
    if not event_loop:
        event_loop = asyncio.new_event_loop()
    explanation = event_loop.run_until_complete(_explain(gateway, why))
    #explanation = asyncio.run(_explain(gateway, why))

    console_whizz(" * Explanation:", end="\n")
    print(textwrap.indent(explanation.decode("utf-8"), "   =  ", predicate=lambda _: True))
