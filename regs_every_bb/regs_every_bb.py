'''
Prints the registers, at every basic block within a range
Contibutors: Toby LLoyd Davies
Copyright (C) 2019 Undo Ltd
'''

from __future__ import print_function
import gdb
from undodb.debugger_extensions import udb

class RegsEveryBB(gdb.Command):
    def __init__(self):
        super(RegsEveryBB, self).__init__('uregs', gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        # Get current time, so we can go back to it afterwards.
        original_time = udb.time.get()

        # Save pagination state
        pagination = gdb.parameter('pagination')

        gdb.execute('set pagination off')

        args = gdb.string_to_argv(arg)

        start_bbcount = int(args[0])
        end_bbcount = int(args[1])

        current_bbcount = start_bbcount

        while current_bbcount <= end_bbcount:
            # Print values of registers at each basic block in range
            udb.time.goto(current_bbcount)
            print('{}:'.format(current_bbcount))
            gdb.execute('info reg')
            print('\n')
            current_bbcount += 1

        # Go back to original time.
        udb.time.goto(original_time)

        # Restore pagination
        if pagination:
            gdb.execute('set pagination on', to_string=True)


RegsEveryBB()
