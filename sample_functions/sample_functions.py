'''
Simpler sampler which uses debug info (via gdb's "where" command)
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

        current_bbcount = start_bbcount

        function_p = re.compile('#0  0x[0-9a-f]+ in (\w+) .*')

        while current_bbcount <= end_bbcount:
            udb.time.goto(current_bbcount)

            # Get backtrace (including current function)
            backtrace = gdb.execute('where', to_string=True)
            backtrace = backtrace.splitlines()

            line = backtrace[0]

            # Line should be like:
            #0  0x00007f0fc6ecc2b0 in fprintf () from /lib/x86_64-linux-gnu/libc.so.6
            m = function_p.match(line)

            # Update current bbcount
            current_bbcount = current_bbcount + interval

            if m is None:
                continue
            function = m.group(1)

            functions[function] += 1

        # Go back to original time.
        udb.time.goto(original_time)

                # Now print what we've found...
        for function in functions.iterkeys():
            print('{} {}'.format(function, str(functions[function])))


SampleFunctions()
