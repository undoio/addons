'''
Prints the registers, at every basic block within a range
Contibutors:  Isa Smith, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
'''

from __future__ import absolute_import, print_function

import gdb

from undodb.debugger_extensions import (
    debugger_utils,
    udb,
    )


class RegsEveryBB(gdb.Command):
    def __init__(self):
        super(RegsEveryBB, self).__init__('uregs', gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        with udb.time.auto_reverting():
            with debugger_utils.temporary_parameter('pagination', False):
                args = gdb.string_to_argv(arg)

                start_bbcount = int(args[0])
                end_bbcount = int(args[1])

                current_bbcount = start_bbcount

                while current_bbcount <= end_bbcount:
                    # Print values of registers at each basic block in range
                    udb.time.goto(current_bbcount)
                    print('{}:'.format(current_bbcount))
                    gdb.execute('info reg')
                    print()
                    current_bbcount += 1


RegsEveryBB()
