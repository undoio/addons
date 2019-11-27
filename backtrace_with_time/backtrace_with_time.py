'''
Adds a ubt command which adds basic block counts to frames within a backtrace.
   Usage: ubt

Contributors: Isa Smith, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
'''


from __future__ import absolute_import, print_function

import gdb

from undodb.debugger_extensions import (
    gdbutils,
    udb,
    )


class BacktraceWithTime(gdb.Command):
    def __init__(self):
        super(BacktraceWithTime, self).__init__('ubt', gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        with udb.time.auto_reverting():
            # Disable all breakpoints, so we can reverse up the stack without
            # hitting anything we shouldn't.
            breakpoints_disabled = []
            for bp in gdb.breakpoints():
                if bp.enabled:
                    breakpoints_disabled.append(bp)
                    bp.enabled = False

            # Get the whole backtrace.
            backtrace = gdbutils.execute_to_string('where')
            backtrace = backtrace.splitlines()

            exception_hit = False
            for line in backtrace:
                if not exception_hit:
                    # Print time at start of each backtrace line.
                    time = udb.time.get()
                    print('[{}]\t{}'.format(str(time.bbcount), line))
                    try:
                        # Go back to previous frame
                        gdbutils.execute_to_string('rf')
                    except gdb.error:
                        # Can't figure out any further - perhaps stack frame is
                        # not available, or we have reached the start.
                        exception_hit = True
                else:
                    print('[?]\t{}'.format(line))

        # Finally, re enable breakpoints.
        for bp in breakpoints_disabled:
            bp.enabled = True


BacktraceWithTime()
