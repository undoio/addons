import functools
import inspect

import gdb
from mcp.server.fastmcp import FastMCP

from src.udbpy.gdb_extensions import command, gdbio, gdbutils, udb_base, udb_last


INSTRUCTIONS = """
This MCP server provides access to the UDB time travel debugger. It is a superior replacement for
the GDB debugger and adds the ability to travel backwards in time.

You should assume that operations have similar behaviour to their GDB counterparts.

# Time travel debugging

Time travel debugging provides two key abilities:

 * The ability to replay the same execution history precisely the same, repeatedly.  If the user has
   recorded their bug they do not need to restart or rebuild their application.
 * The ability to rewind execution history.  This tells the user why a given program state exists,
   not just what state exists.

To debug effectively, you should start by recording the bug.  Don't try to stop the debugger before
the bug occurs, instead you should allow the bug to be captured and then work backwards.

# Running UDB

UDB is already run under the control of the server.

## Start and end of history

If you see the message "Have reached start of recorded history." it means you've got too far back in
history.  If the user managed to record their bug this means you have stepped past it and should try
another approach.

Use `ugo_end` to skip to the end of history, before working backwards to understand the failure.

## Navigating the stack

Use `backtrace` to find out what function you are in and what called it.

Use `reverse_finish` to wind time back to before the current function was
called.  You can apply this repeatedly.

```
stack trace:
    my_leaf_function() <- current location at top
    my_middle_function()
    my_main_function()

debug tool:
    reverse_finish

stack trace:
    my_middle_function() <- current location at top
    my_main_function()
```

## The standard library

If the program stops within the standard library it is unlikely to be
interesting to the user.  You should use `reverse_finish` to step out of it and
back to user code.

## Navigating function calls

After using `reverse_step` check that you are in the function you expected.

Use `reverse_next` to step backwards over a function as it is called.

```
Source context:
   10   int my_value = called_function()
   ->
   11   a = a + b;

UDB:reverse_next

Source context:
    9
   ->
   10 int my_value = called_function()
   11 a = a + b;
```

## Inspecting values

Use `last` to wind back time to find out how and when a value was set.

```
source lines:
    int my_value = called_function()

    ... many other lines skipped ...

    printf("My value is %d\n", my_value); <- debug location

debug tool:
    last my_value

source lines:
    int my_value = called_function() <- debug location
```

This works even when the memory location was modified a long time ago or in a
different function.

When `last` returns it specifies a "Was" value, which is what you were
investigating.  "Now" is the previous value, which should be ignored or used
for a new debugging hypothesis.

`last` will only work for values that are currently in scope.  If a value is not
currently in scope then you need to navigate backwards in time until it is.  Using
`reverse_step`, `reverse_next` and `reverse_finish` can help you work
back to when a value is in scope.

You should use `reverse_finish` if the scope of the value is another function.
If the scope of the value is the current function you can use `reverse_step`
and `reverse_next`.

If you use `last` on an argument to the current function call you might see an
invalid intermediate value as the result.  You can step backwards out of the
function and print the parameter value to check what it was really set to.

Use `print` to find out the current value of a variable.  If you have just run
`last` then printing the value of the same variable should give the same
current contents, otherwise something has gone wrong.

## Understanding `if` statements

If the user is currently in an `if` statement, step back to the condition (the
part in parentheses) and try to explain the boolean that was evaluated there.

You could step back to the condition using `reverse_next`.

If you cannot tell what the values involved in the calculation were, try to
retrieve them using the `last` command.

```
source lines:
    if (a != b) {
        calculate_further_values()

        ... skipped other lines ...

        assert(bad); <- debug location
    }

debug tool:
    reverse_next (repeat as needed)

source lines:
    if (a != b) { <- debug location
        calculate_further_values()
        ... skipped other lines ...

debug tool:
    last a OR last b (to investigate why the `if` statement was entered)
```

# Explaining a bug

To diagnose the bug follow the following procedure:

 1. Hypothesis: Form a hypothesis about why the bug occurred.  Start with getting a `backtrace`.
 2. Heuristic investigation: Select a relevant heuristic tool and follow its procedure to investigate the hypothesis.
 3. Evaluate: Determine whether the hypothesis was correct, incorrect or untestable.
 4a. If the bug has been root caused, report to the user.
 4b. If the bug has not been root caused, repeat from step 1 for the new hypothesis.
"""


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

    start_line = max(0, line - SOURCE_CONTEXT)
    end_line = min(len(lines), line + SOURCE_CONTEXT)

    formatted_lines = list(f"{i: 5d} {lines[i].rstrip()}" for i in range(start_line, end_line))
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

        context = f"\n\nFunction: {frame.name()}\n"

        if sal and sal.symtab:
            context += "\n\nSource context:\n\n" + get_context(sal.symtab.filename, sal.line)
        else:
            context += "\n\nSource context unavailable.\n"

        return out + context

    return wrapped


def chain_of_thought(fn):
    """
    Add chain-of-thought parameters and documentation to the wrapped function.

    This requires the LLM to explain its reasoning as it goes along, leading to better or more
    understandable results.
    """
    @functools.wraps(fn)
    def wrapped(self, theory: str, hypothesis: str, *args, **kwargs):
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
    def __init__(self, udb: udb_base.Udb, mcp: FastMCP):
        self.udb = udb
        self.mcp = mcp

        self._register_tools()


    def _register_tools(self) -> None:
        for name, fn in inspect.getmembers(self, inspect.ismethod):
            if not name.startswith("tool_"):
                continue
            self.mcp.add_tool(fn=fn, name=name.removeprefix("tool_"), description=fn.__doc__)


    @chain_of_thought
    def tool_get_time(self) -> str:
        """
        Get the current point in recorded history.
        """
        return str(self.udb.time.get())


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


    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_finish(self) -> str:
        """
        Run backwards to before the current function was called.
        """
        self.udb.execution.reverse_finish(cmd="reverse-finish")


    @source_context
    @collect_output
    @chain_of_thought
    def tool_reverse_step(self, intended_function: str) -> str:
        """
        Step into the return path of a function on an earlier line of source code.

        `reverse_step` will step backwards into a function on the previous line.
        You may need to issue `reverse_step` more than once to reach the `return` statement.
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
        self.udb.execution.reverse_step(cmd="reverse-step")

    @chain_of_thought
    def tool_backtrace(self) -> str:
        """
        Get a backtrace of the code at the current point in time.
        """
        return gdbutils.execute_to_string("backtrace")

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
    mcp = FastMCP("UDB Server", instructions=INSTRUCTIONS)
    gateway = UdbMcpGateway(udb, mcp)
    gateway.mcp.run(transport="sse")
