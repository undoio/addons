'''
Sampler which uses debug info (via gdb's "where" command)
together with UndoDB's ugo command to count the number of times we find
ourselves in a particular function.

Usage:
   usample <start_bbcount> <end_bbcount> <bbcount_interval>
   E.g. 1 1000 1
    means sample every basic block from 1 to 1000.

Contributers: Isa Smith, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
'''


from __future__ import absolute_import, division, print_function

import re
from collections import defaultdict

import gdb

from undodb.debugger_extensions import udb


class SampleFunctions(gdb.Command):
    '''
    Advance through the debuggee, sampling the function we are currently in.
    '''

    def __init__(self):
        super(SampleFunctions, self).__init__('usample', gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        '''
        arg is:
        <start_bbcount> <end_bbcount> <bbcount_interval>
        E.g. 0 1000 1
        means sample every basic block from 1 to 1000.
        '''

        # Get original time so that we can restore it
        original_time = udb.time.get()

        functions = defaultdict(lambda: 0)

        args = gdb.string_to_argv(arg)

        start_bbcount = int(args[0])
        end_bbcount = int(args[1])
        interval = int(args[2])

        function_p = re.compile(r'#[0-9]+  ([^\s]+) \(.*\) (at|from) .*')

        # Save print address value so that we can restore it
        print_address = gdb.parameter('print address')
        gdb.execute('set print address off', to_string=True)

        for current_bbcount in range(start_bbcount, end_bbcount + 1, interval):
            udb.time.goto(current_bbcount)
            frame = gdb.newest_frame()
            # Create list of functions in the backtrace
            trace_functions = []
            while frame is not None:
                trace_functions.append(frame.name())
                frame = frame.older()
            # Concatenate functions in backtrace to create key
            key = '->'.join(reversed(trace_functions))
            functions[key] += 1

        # Restore original value of print address
        if print_address:
            gdb.execute('set print address on', to_string=True)

        # Go back to original time.
        udb.time.goto(original_time)

        # Now print what we've found...
        for function in functions:
            print('{} {}'.format(function, str(functions[function])))


SampleFunctions()
