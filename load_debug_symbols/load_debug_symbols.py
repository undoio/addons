'''Utility that loads a debug symbol file by parsing .text. .data and .bss section addresses'''

from __future__ import absolute_import, print_function

import os
import re
import gdb

# Pattern to match output of 'info files'
pattern = re.compile(
    r'(?P<begin>[0x0-9a-fA-F]+)\s-\s(?P<end>[0x0-9a-fA-F]+)'
    r'\s\bis\b\s(?P<section>\.[a-z]+$)')


def parse_sections():
    file_info = gdb.execute('info files', to_string=True)
    section_map = {}
    for line in file_info.splitlines():
        line = line.strip()
        m = re.match(pattern, line)
        if m is None:
            continue

        section = m.group('section')
        if section not in ('.text', '.data', '.bss'):
            continue
        begin = m.group('begin')
        section_map[section] = begin

    return section_map


def load_sym_file_at_addrs(dbg_file, smap):
    cmd = 'add-symbol-file {} {} -s .data {} -s .bss {}'.format(
        dbg_file, smap['.text'], smap['.data'], smap['.bss'])
    gdb.execute(cmd)


class LoadDebugFile(gdb.Command):
    '''
    Loads the debug symbol file with the correct address for .text
    .data and .bss sections.
    '''

    def __init__(self):
        super(LoadDebugFile, self).__init__('load-debug-symbols', gdb.COMPLETE_EXPRESSION)

    @staticmethod
    def invoke(args, from_tty):
        arglist = args.split()
        if len(arglist) != 1:
            print('Usage: load-debug-symbols <file_path>')
            return

        dbg_file = arglist[0]
        if not os.path.exists(dbg_file):
            print('{} is not a valid file path'.format(dbg_file))
            return

        section_map = parse_sections()
        load_sym_file_at_addrs(dbg_file, section_map)


LoadDebugFile()
