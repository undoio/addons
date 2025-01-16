
import re
import gdb
from addons.utils import locate_api
locate_api()
from src.udbpy import report, termstyles
from src.udbpy.gdb_extensions import command, command_args, gdbio, gdbutils, udb_base
from undo.debugger_extensions import udb
udb = udb._wrapped_udb  # pylint: disable=protected-access,redefined-outer-name

def _get_block_vars(frame: gdb.Frame, block: gdb.Block) -> dict[str, gdb.Value]:
    """Fetch all variable values for the given block."""

    vals = {var.print_name: var.value(frame) for var in block}

    # Force values to be evaluated from debuggee before we move in time
    for val in vals.values():
        val.fetch_lazy()

    return vals


def _get_local_vars(frame: gdb.Frame = None) -> dict[str, gdb.Value]:
    """Fetch all local variables in the given (or current) scope."""

    if frame is None:
        frame = gdbutils.newest_frame()
    block = frame.block()
    vals: dict[str, gdb.Value] = {}

    # Iterate out from the current block until function scope is reached.
    # Variables from each scope level are collected; in the event of a name
    # clash, the inner scope is preferred.
    while True:
        vals = _get_block_vars(frame, block) | vals
        if block.function:
            break
        assert block.superblock is not None
        block = block.superblock

    # Force values to be evaluated from debuggee now
    for val in vals.values():
        val.fetch_lazy()

    return vals

def _print(text: str)-> None:
    """Print variable changes in a consistent style."""
    report.user(text, foreground=termstyles.Color.CYAN)

def _print_var_diffs(before_vals: dict[str, gdb.Value], after_vals: dict[str, gdb.Value],
                     reverse_op: bool = False) -> None:
    changed_vals = {
        var: val for var, val in after_vals.items() if (var, val) not in before_vals.items()
    }
    arrow = "<-" if reverse_op else "->"
    for var, val in changed_vals.items():
        prev_val = before_vals.get(var, "")
        _print(f"{var} {prev_val} {arrow} {val}")


@command.register(
    gdb.COMMAND_STATUS,
)
def value_tracer_next(udb: udb_base.Udb) -> None:
    """
    Report variable changes as a result of running the current line.
    """

    # TODO: consider allowing user to specify command name
    # TODO: consider how to hook onto other commands

    with (
        gdbutils.breakpoints_suspended(),
        udb.replay_standard_streams.temporary_set(False),
        gdbio.CollectOutput(),
        udb.time.auto_reverting(),
    ):
        before_vals = _get_local_vars()

        udb.execution.next()
        after_vals = _get_local_vars()

    if before_vals or after_vals:
        _print_var_diffs(before_vals, after_vals)
    else:
        _print("No changes.")

forward_ops = ["c", "continue",
       "fin", "finish",
       "n", "next",
       "ni", "nexti",
       "s", "step",
       "si", "stepi",
       "until",
]
reverse_ops = [
       "rc", "reverse-continue",
       "rfin", "reverse-finish",
       "rn", "reverse-next",
       "rni", "reverse-nexti",
       "rs", "reverse-step",
       "rsi", "reverse-stepi",
       "reverse-until",
]

def _execution_op_with_locals(cmd: str, quiet: bool=False) -> None:
    """
    Perform a (reverse) execution operation showing locals before and after.
    """

    before_vals = _get_local_vars()
    frame = gdbutils.newest_frame()
    gdb.execute(cmd, to_string=True)
    if gdbutils.newest_frame() != frame:
        return
    after_vals = _get_local_vars()

    if before_vals == after_vals:
        if not quiet:
            report.user("No changes.")
    else:
        _print_var_diffs(before_vals, after_vals, cmd in reverse_ops)

@command.register(
    gdb.COMMAND_STATUS, arg_parser=command_args.Choice(forward_ops+reverse_ops)
)
def value_tracer(udb: udb_base.Udb, cmd: str) -> None:
    """
    Perform a (reverse) execution operation showing locals before and after.
    """
    _execution_op_with_locals(cmd)


@command.register(
    gdb.COMMAND_STATUS,
)
def value_tracer_function(udb: udb_base.Udb) -> None:
    """
    Report function history line by line, showing changes to locals.
    """

    with (
        udb.time.auto_reverting(),
        gdbutils.temporary_parameter("print frame-info", "source-line"),
    ):
        # Find start of function
        with (
            gdbutils.breakpoints_suspended(),
            udb.replay_standard_streams.temporary_set(False),
            gdbio.CollectOutput(),
        ):
            udb.execution.reverse_finish(cmd="auto-locals-function")
            udb.execution.step()

        # Step through function
        frame = gdbutils.newest_frame()
        report.user(f"        {frame.name()}(...)")
        report.user("        {")
        while True:
            gdb.execute("frame")
            _execution_op_with_locals("next", quiet=True)
            if gdbutils.newest_frame() != frame:
                break

        report.user("        }")

show_references: bool = False

@command.register(gdb.COMMAND_STATUS)
def value_tracer_inline(udb: udb_base.Udb) -> None:
    """
    Report function history line by line, with inline value annotations.
    """

    with (
        # Return to current time when done.
        udb.time.auto_reverting(),
        # Only print the source line when executing `frame`.
        gdbutils.temporary_parameter("print frame-info", "source-line"),
    ):
        # Find start of function
        with (
            gdbutils.breakpoints_suspended(),
            udb.replay_standard_streams.temporary_set(False),
            gdbio.CollectOutput(),
        ):
            udb.execution.reverse_finish(cmd="auto-locals-function")
            udb.execution.step()

        # Step through function
        frame = gdbutils.newest_frame()
        report.user(f"        {frame.name()}(...)")
        report.user("        {")
        while True:
            code_line = gdbutils.execute_to_string("frame")
            code_line = termstyles.strip_ansi_escape_codes(code_line)
            frame = gdbutils.newest_frame()
            gdb.execute("next", to_string=True)
            if gdbutils.newest_frame() != frame:
                break

            for name, value in _get_local_vars().items():
                tag = termstyles.ansi_format(f"«{value}»", intensity=termstyles.Intensity.DIM)
                if show_references:
                    # Match "foo", but not "bar.foo", "food", "otherfoo"
                    # FIXME: Fails to match in the case of "if (bar>foo)"
                    # TODO: Can treesitter or similar be used to parse the line?
                    annotate_re =  fr"(?<!\.|\>|[a-zA-Z0-9_])(?P<orig>\s*{name})(?![a-zA-Z0-9_])"
                    annotate_lambda = lambda m: f"{m['orig']} {tag}"
                else:
                    # The RE aims to recognise "foo=", but not "bar->foo=" or "foo=="
                    annotate_re =  fr"(?<!\.|\>)(?P<orig>\s*{name})\s*=(?!=)"
                    annotate_lambda = lambda m: f"{m['orig']} {tag} ="
                code_line = re.sub(annotate_re, annotate_lambda, code_line)
            report.user(code_line)

        report.user("        }")

@command.register(gdb.COMMAND_DATA, arg_parser=command_args.Boolean())
def set__value_tracer_inline_references(udb: udb_base.Udb, on: bool) -> None:
    """Set whether value-tracer-inline annotates all references to local variables."""
    global show_references
    show_references = on

@command.register(gdb.COMMAND_STATUS)
def show__value_tracer_inline_references(udb: udb_base.Udb) -> None:
    """Show whether value-tracer-inline annotates all references to local variables."""
    if show_references:
        report.user("Values of local variables are shown whenever referenced.")
    else:
        report.user("Values of local variables are shown only on assignment.")
