"""
Undo Automation extension module for tracking calls to malloc() and free() and checking for
leaked memory.

This script only support the x86-64 architecture.

Contributors: Chris Croft-White, Magne Hov
"""

import collections
import re

import gdb

from undodb.debugger_extensions import udb
from undodb.debugger_extensions.debugger_io import redirect_to_launcher_output


def leak_check() -> None:
    """
    Implements breakpoints and stops on all calls to malloc() and free(), capturing the
    timestamp, size and returned pointer for malloc(), then confirms the address pointer is later
    seen in a free() call.

    If a subsequent free() is not seen, then at the end of execution, output the timestamp and
    details of the memory which was never freed.
    """
    # Set a breakpoint for the specified function.
    gdb.Breakpoint("malloc")
    gdb.Breakpoint("free")

    # Declare allocations dictionary structure.
    allocations = collections.OrderedDict()

    # Do "continue" until we have gone through the whole recording, potentially
    # hitting the breakpoints several times.
    end_of_time = udb.get_event_log_extent().end
    while True:
        gdb.execute("continue")

        # Rather than having the check directly in the while condition we have
        # it here as we don't want to print the backtrace when we hit the end of
        # the recording but only when we stop at a breakpoint.
        if udb.time.get().bbcount >= end_of_time:
            break

        # Use the $PC output to get the symbol and idenfity whether execution has stopped
        # at a malloc() or free() call.
        mypc = format(gdb.parse_and_eval("$pc"))
        if re.search("malloc", mypc):
            # In malloc(), set a FinishBreakpoint to capture the pointer returned later.
            mfbp = gdb.FinishBreakpoint()

            # For now, capture the timestamp and size of memory requested.
            time = udb.time.get()
            size = gdb.parse_and_eval("$rdi")

            gdb.execute("continue")

            # Should stop at the finish breakpoint, so capture the pointer.
            addr = mfbp.return_value

            if addr:
                # Store details in the dictionary.
                allocations[format(addr)] = time, size
            else:
                print(f"-- INFO: Malloc called for {size} byte(s) but null returned.")

            print(f"{time}: malloc() called: {size} byte(s) allocated at {addr}.")

        elif re.search("free", mypc):
            # In free(), get the pointer address.
            addr = gdb.parse_and_eval("$rdi")

            time = udb.time.get()

            # Delete entry from the dictionary as this memory was released.
            if addr > 0:
                if allocations[hex(int(format(addr)))]:
                    del allocations[hex(int(format(addr)))]
                else:
                    print("--- INFO: Free called with unknown address")
            else:
                print("--- INFO: Free called with null address")

            # with redirect_to_launcher_output():
            print(f"{time}: free() called for {int(addr):#x}")

    # If Allocations has any entries remaining, they were not released.
    with redirect_to_launcher_output():
        print()
        print(f"{len(allocations)} unmatched memory allocation(s):")
        print()

        total = 0

        # Increase the amount of source from default (10) to 16 lines for more context.
        gdb.execute("set listsize 16")
        for addr in allocations:
            time, size = allocations[addr]
            total += size
            print("===============================================================================")
            print(f"{time}: {size} bytes was allocated at {addr}, but never freed.")
            print("===============================================================================")
            udb.time.goto(time)
            print("Backtrace:")
            gdb.execute("backtrace")
            print()
            print("Source (if available):")
            gdb.execute("finish")
            gdb.execute("list")
            print()
            print("Locals (after malloc returns):")
            gdb.execute("info locals")
            print()
            print()
        print("===============================================================================")
        print(f"  In total, {total} byte(s) were allocated and not released")
        print()

    return len(allocations)


# UDB will automatically load the modules passed to UdbLauncher.add_extension and, if present,
# automatically execute any function (with no arguments) called "run".
def run() -> None:
    # Needed to allow GDB to fixup breakpoints properly after glibc has been loaded
    gdb.Breakpoint("main")

    unmatched = leak_check()

    # Pass the number of time we hit the breakpoint back to the outer script.
    udb.result_data["unmatched"] = unmatched
