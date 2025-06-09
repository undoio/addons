"""
Sampler which uses debug info (via gdb's "where" command)
together with UDB's ugo command to count the number of times we find
ourselves in a particular function.

Usage:
   usample <start_bbcount> <end_bbcount> <bbcount_interval>
   E.g. 1 1000 1
    means sample every basic block from 1 to 1000.

Contributers: Isa Smith, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
"""

import sys

from collections import defaultdict

import gdb

from undo.debugger_extensions import (
    debugger_utils,
    udb,
)


class SampleFunctions(gdb.Command):
    """
    Advance through the debuggee, sampling the function we are currently in.
    """

    def __init__(self):
        super().__init__("usample", gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        """
        arg is:
        <start_bbcount> <end_bbcount> <bbcount_interval> [<filename>]
        E.g. 0 1000 1
        means sample every basic block from 1 to 1000.
        """
        with udb.time.auto_reverting():
            functions = defaultdict(lambda: 0)

            args = gdb.string_to_argv(arg)

            start_bbcount = int(args[0])
            end_bbcount = int(args[1])
            interval = int(args[2])

            if len(args) > 3:
                output = open(args[3], "wt")  # pylint:disable=consider-using-with
            else:
                output = sys.stdout

            with debugger_utils.temporary_parameter("print address", False):
                for current_bbcount in range(start_bbcount, end_bbcount + 1, interval):
                    udb.time.goto(current_bbcount)
                    frame = gdb.newest_frame()
                    # Create list of functions in the backtrace
                    trace_functions = []
                    while frame is not None:
                        if frame.name() is not None:
                            trace_functions.append(frame.name())
                        else:
                            # If no symbol for function use pc
                            trace_functions.append(hex(frame.pc()))
                        frame = frame.older()
                    # Concatenate functions in backtrace to create key
                    key = ";".join(reversed(trace_functions))
                    functions[key] += 1

        # Now print what we've found...
        for function in functions:
            print("{} {}".format(function, str(functions[function])), file=output)


SampleFunctions()
