import datetime
import re

import gdb

from undo.debugger_extensions import (
    debugger_utils,
    udb,
)


class WallclockRelative(gdb.Command):
    """
    Adds an info wallclock-relative command which prints the approximate wallclock
    time relative to the start of recording.
        Usage: info wallclock-relative
    """

    def __init__(self):
        super().__init__("info wallclock-relative", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        extents = debugger_utils.execute_to_string("info wallclock-extent")
        m = re.search("Start time: (.*)", extents)
        if not m:
            raise gdb.GdbError("Could not determine start time.")

        # e.g. 2024-07-02T12:28:33Z
        start_time = datetime.datetime.strptime(m[1], "%Y-%m-%dT%H:%M:%SZ")
        start_delta = datetime.timedelta(
            hours=start_time.hour,
            minutes=start_time.minute,
            seconds=start_time.second,
        )
        current = debugger_utils.execute_to_string("info wallclock")
        # e.g. 2024-07-16T11:39:39.888096Z (approximate)
        m = re.search("T(.*)Z", current)
        if not m:
            raise gdb.GdbError("Could not determine current time.")

        current_time = datetime.datetime.strptime(m[1], "%H:%M:%S.%f")
        current_delta = datetime.timedelta(
            hours=current_time.hour,
            minutes=current_time.minute,
            seconds=current_time.second,
            microseconds=current_time.microsecond,
        )
        relative_delta = current_delta - start_delta
        print(f"Relative: {relative_delta}")


WallclockRelative()
