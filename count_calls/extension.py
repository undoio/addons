from __future__ import absolute_import, division, print_function

import gdb

from undodb.debugger_extensions import udb


def run():
    # The function where to stopped is passed to us form the outer script
    # in the run_data dictionary.
    func_name = udb.run_data['func_name']
    # Set a breakpoint for the specified function.
    bp = gdb.Breakpoint(func_name)

    # Do "continue" until we have gone through the whole recording, potentially
    # hitting the breakpoint several times.
    end_of_time = udb.get_event_log_extent().max_bbcount
    while udb.time.get().bbcount < end_of_time:
        gdb.execute('continue')

    # Pass the number of time we hit the breakpoint back to the outer script.
    udb.result_data['hit-count'] = bp.hit_count
