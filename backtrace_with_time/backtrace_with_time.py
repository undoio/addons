"""
Adds a ubt command which adds basic block counts to frames within a backtrace.
   Usage: ubt

Contributors: Isa Smith, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
"""

import gdb

from undodb.debugger_extensions import (
    debugger_utils,
    udb,
)


class BacktraceWithTime(gdb.Command):
    def __init__(self):
        super().__init__("ubt", gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        # We disable all breakpoints, so we can reverse up the stack without
        # hitting anything we shouldn't.
        with udb.time.auto_reverting(), debugger_utils.breakpoints_suspended():
            # Get the whole backtrace.
            backtrace = debugger_utils.execute_to_string("where", styled=True)
            backtrace = backtrace.splitlines()

            # The bbcount now is the largest that will be printed, so
            # it can define the width of the column
            bbcount_width = len(str(udb.time.get().bbcount))

            exception_hit = False
            for line in backtrace:
                if not exception_hit:
                    # Print time at start of each backtrace line.
                    time = udb.time.get()
                    print(f"[{time.bbcount:{bbcount_width}}] {line}")
                    try:
                        # Go back to previous frame
                        debugger_utils.execute_to_string("rf")
                    except gdb.error:
                        # Can't figure out any further - perhaps stack frame is
                        # not available, or we have reached the start.
                        exception_hit = True
                else:
                    print(f"[?]\t{line}")


BacktraceWithTime()
