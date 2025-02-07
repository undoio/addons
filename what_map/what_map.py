"""
Implementation of the "whatmap" utility command for GDB and UDB.
    Usage: whatmap EXPRESSION

Contributors: Mark Willamson, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
"""

import tempfile
import re
import gdb

# Pattern to parse map.
begin_pattern = re.compile(r"\s+0x(?P<begin>[0-9a-f]+)\s+0x(?P<end>[0-9a-f]+).*")


def find_map(address):
    """
    Look up a specified address in the /proc/PID/maps for a process.

    Returns: A string representing the map in question, or None if no match.
    """
    maps = gdb.execute("info proc mappings", to_string=True)
    for m in re.finditer(begin_pattern, maps):
        begin = int(m.group("begin"), 16)
        end = int(m.group("end"), 16)

        if begin <= address < end:
            # For some reason lines returned from info proc mappings start
            # with a newline character
            return m.group(0).lstrip('\n')

    return None


class WhatMapCommand(gdb.Command):
    """
    A command to look up a variable or address within the maps of the debuggee.
    Usage: whatmap EXPRESSION
    """

    def __init__(self):
        super().__init__("whatmap", gdb.COMPLETE_EXPRESSION)

    @staticmethod
    def invoke(argument, from_tty):
        try:
            value = gdb.parse_and_eval(argument)
        except gdb.error:
            # is this a register?
            print(f"arg is {argument}")
            address = int(gdb.selected_frame().read_register(argument))
        else: 
            uintptr_type = gdb.lookup_type("unsigned long")

            if value.address is None:
                raise gdb.GdbError('Expression "{}" is not addressable.'.format(argument))

            # For a value that has an address within the program, we can look up
            # that address within the maps.
            # This allows the user to e.g. just specify a variable name.
            address = int(value.address.cast(uintptr_type))

        print(f"Searching maps for address 0x{address:x}:")
        _map = find_map(address)
        if _map:
            print("    " + _map)
        else:
            print("    No such map.")


WhatMapCommand()
