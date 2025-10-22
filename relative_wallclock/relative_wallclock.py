import datetime
import re

import gdb
from undo.debugger_extensions import debugger_utils


def str_to_delta(wallclock: str) -> datetime.timedelta:
    """
    Converts a string from `info wallclock` or `info wallclock-extent` into a datetime.timedelta.
    Accepts strings in the format H:M:S.microsecond used by Undo 8.2, and %H:%M:%S used by
    info wallclock-extent in earlier versions.
    """
    try:
        # Undo 8.2 and later
        # e.g. 2024-07-16T11:39:39.888096Z
        t = datetime.datetime.strptime(wallclock, "%H:%M:%S.%f")
    except ValueError:
        # Undo earlier than 8.2.
        # e.g. 2024-07-02T12:28:33Z
        t = datetime.datetime.strptime(wallclock, "%H:%M:%S")

    delta = datetime.timedelta(
        hours=t.hour,
        minutes=t.minute,
        seconds=t.second,
        microseconds=t.microsecond,
    )
    return delta


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
        m = re.search("Start time: .*T(.*)Z", extents)
        if not m:
            raise gdb.GdbError("Could not determine start time.")

        start_delta = str_to_delta(m[1])

        current = debugger_utils.execute_to_string("info wallclock")
        # e.g. 2024-07-16T11:39:39.888096Z (approximate)
        m = re.search("T(.*)Z", current)
        if not m:
            raise gdb.GdbError("Could not determine current time.")

        current_delta = str_to_delta(m[1])

        relative_delta = current_delta - start_delta
        print(f"Relative: {relative_delta}")


WallclockRelative()
