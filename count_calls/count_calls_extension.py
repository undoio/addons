from __future__ import absolute_import, division, print_function

import gdb

from undodb.debugger_extensions import udb


def count_calls(func_name):
    '''
    Counts how many times func_name is hit during the replay of the currently
    loaded recording and returns the hit count.
    '''
    # Set a breakpoint for the specified function.
    bp = gdb.Breakpoint(func_name)

    # Do "continue" until we have gone through the whole recording, potentially
    # hitting the breakpoint several times.
    end_of_time = udb.get_event_log_extent().max_bbcount
    while udb.time.get().bbcount < end_of_time:
        gdb.execute('continue')

    return bp.hit_count


# UndoDB will automatically load the modules passed to UdbLauncher.add_extension
# and, if present, automatically execute any function (with no arguments) called
# "run".
def run():
    # The function where to stop is passed to us from the outer script in the
    # run_data dictionary.
    func_name = udb.run_data['func_name']

    hit_count = count_calls(func_name)

    # Pass the number of time we hit the breakpoint back to the outer script.
    udb.result_data['hit-count'] = hit_count
