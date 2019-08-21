'''
Implementation of the "whatmap" utility command for GDB and UDB.
    Usage: whatmap EXPRESSION

Contributors: Mark Willamson, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
'''

from __future__ import absolute_import, print_function

import tempfile
import re
import gdb

# Pattern to parse map.
begin_pattern = re.compile(
    r'(?P<begin>[0-9a-fA-F]+)-(?P<end>[0-9a-fA-F]+)'
    r'\s+([rwxps-]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+)\s+'
    r'([0-9]+)[ ]*([^\n]*)')


def fetch_maps_remote():
    '''
    Fetch the contents of /proc/PID/maps from a remote debug server.
    '''
    with tempfile.NamedTemporaryFile(mode='r', delete=True) as maps:
        pid = gdb.selected_inferior().pid
        gdb.execute('remote get /proc/{}/maps {}'.format(pid, maps.name))
        return maps.read()


def fetch_maps_local():
    '''
    Fetch the contents of a /proc/PID/maps for a debuggee
    without using a remote debug server.
    '''
    pid = gdb.selected_inferior().pid
    with open('/proc/{}/maps'.format(pid)) as maps:
        return maps.read()


def fetch_maps():
    '''
    Fetch the maps of the current inferior - preferring to go via debug server,
    if possible.
    '''
    try:
        # Try to fetch maps from a remote debug server.
        # If we're not using a remote server, this will throw an exception
        # and we'll fall back to the local implementation.
        return fetch_maps_remote()
    except gdb.error:
        # Try to fetch maps from the current inferior PID by reading the local
        # /proc/PID/maps file directly.
        return fetch_maps_local()


def find_map(address):
    '''
    Look up a specified address in the /proc/PID/maps for a process.

    Returns: A string representing the map in question, or None if no match.
    '''
    maps = fetch_maps()
    for m in re.finditer(begin_pattern, maps):
        begin = int(m.group('begin'), 16)
        end = int(m.group('end'), 16)

        if begin <= address < end:
            return m.group(0)

    return None


class WhatMapCommand(gdb.Command):
    '''
    A command to look up a variable or address within the maps of the debuggee.
    Usage: whatmap EXPRESSION
    '''

    def __init__(self):
        super(WhatMapCommand, self).__init__('whatmap',
                                             gdb.COMPLETE_EXPRESSION)

    @staticmethod
    def invoke(argument, from_tty):
        value = gdb.parse_and_eval(argument)
        uintptr_type = gdb.lookup_type('unsigned long')

        if value.address is None:
            raise gdb.GdbError('Expression "{}" is not addressable.'
                               .format(argument))

        # For a value that has an address within the program, we can look up
        # that address within the maps.
        # This allows the user to e.g. just specify a variable name.
        address = int(value.address.cast(uintptr_type))

        print('Searching maps for address 0x{:x}:'.format(address))
        _map = find_map(address)
        if _map:
            print('    ' + _map)
        else:
            print('    No such map.')


WhatMapCommand()
