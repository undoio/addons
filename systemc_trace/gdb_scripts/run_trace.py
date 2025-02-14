# Created by ripopov
# Modified by Undo

import dataclasses
from pathlib import Path

import gdb
from src.udbpy import report
from src.udbpy.gdb_extensions import command, command_args, gdbio, gdbutils, udb_base

from . import sc_design


@dataclasses.dataclass
class SystemcTraceConfig:

    signals_file: Path | None = None


_config = SystemcTraceConfig()


class Sim:

    def __init__(self, udb: udb_base.Udb) -> None:

        self.udb = udb
        print("SystemC Full trace")

        with (
            gdbutils.breakpoints_suspended(),
            gdbutils.temporary_breakpoints(),
            self.udb.time.auto_reverting(),
            gdbio.CollectOutput(),
            self.udb.replay_standard_streams.temporary_set(False),
        ):
            gdb.execute("ugo start")
            # Intermediate breakpoint at main required for dynamic linking, otherwise
            # required SystemC symbols won't be found
            bp_main = gdb.Breakpoint("main")
            gdb.execute("continue")

            simcontext_ptr = gdb.lookup_symbol("sc_core::sc_curr_simcontext")[0]
            assert isinstance(simcontext_ptr, gdb.Symbol)
            self.simctx = simcontext_ptr.value().dereference()
            bp_main.enabled = False

            bp_start = gdb.Breakpoint("*sc_core::sc_simcontext::prepare_to_simulate")

            gdb.execute("continue")
            bp_start.enabled = False

            self.design = sc_design.SCModule(self.simctx)

    def do_run_simulation(self, *, trace_file: Path | None = None) -> None:
        """Run the simulation and extract signals to the specified file."""

        trace_file = trace_file or Path("systemc_trace.vcd")
        timescale = int(self.simctx["m_time_params"].dereference()["time_resolution"])
        if _config.signals_file:
            signals = _config.signals_file.read_text().splitlines()
            tf = self.design.trace_signals(timescale, trace_file, signals)
        else:
            tf = self.design.trace_all(timescale, trace_file)

        try:
            with (
                gdbutils.breakpoints_suspended(),
                gdbutils.temporary_breakpoints(),
                self.udb.time.auto_reverting(),
            ):
                gdb.execute("ugo start")
                bp_trace = gdb.Breakpoint("sc_simcontext::do_timestep")
                for l in bp_trace.locations:
                    if l.function and "@plt" in l.function:
                        l.enabled = False

                while True:
                    output = gdbutils.execute_to_string("continue")
                    if "Have reached end of recorded history" in output:
                        break
                    tf.collect_now(self.simctx)

        finally:
            tf.done()


command.register_prefix(
    "systemc",
    gdb.COMMAND_STATUS,
    """
    Commands for working with SystemC recordings.
    """,
)


@command.register(gdb.COMMAND_STATUS)
def systemc__print(udb: udb_base.Udb) -> None:
    """Display the design hierarchy."""

    sim = Sim(udb)
    print(sim.design)


@command.register(gdb.COMMAND_STATUS)
def systemc__list_signals(udb: udb_base.Udb) -> None:
    """List all the signals in the design."""

    sim = Sim(udb)
    print("\nList of all detected signals:\n")
    sim.design.print_members()


@command.register(gdb.COMMAND_STATUS, arg_parser=command_args.Filename(default=None))
def systemc__run(udb: udb_base.Udb, filename: Path | None) -> None:
    """Run the simulation and extract signals to the specified file."""

    sim = Sim(udb)
    sim.do_run_simulation(trace_file=filename)


@command.register(gdb.COMMAND_DATA, arg_parser=command_args.Filename())
def set__signals_file(udb: udb_base.Udb, file: Path) -> None:
    """
    Set the file containing a list of signals to trace.

    Usage: set signals-file FILE
    """
    _config.signals_file = file


@command.register(gdb.COMMAND_DATA)
def unset__signals_file(udb: udb_base.Udb) -> None:
    """
    Unset the currently configured signals file. All signals will be traced.
    """
    _config.signals_file = None


@command.register(gdb.COMMAND_STATUS)
def show__signals_file(udb: udb_base.Udb) -> None:
    """
    Show the currently configured signals file.
    """

    if _config.signals_file:
        report.user(f"signals file: {str(_config.signals_file)!r}")
    else:
        report.user("No signals file.")
