from __future__ import absolute_import, print_function

import re
import subprocess
from subprocess import PIPE
import datetime
from collections import namedtuple
import traceback
import six

import gdb

PROFILING = False


def parse_raw_symlist(syml):
    symre = r'[0-9 ]+\s[\w]\s(.*)'
    symc = re.compile(symre)
    for line in syml.split('\n'):
        m = symc.search(line)
        if m:
            yield m.group(1)


def extract_symbol_list_from_so(file_name):
    try:
        symlist = subprocess.check_output(['nm', '-C', file_name], stderr=PIPE)
        if not symlist:
            pdb_name = file_name.replace('.so', '.pdb')
            symlist = subprocess.check_output(['nm', '-C', pdb_name], stderr=PIPE)
    except subprocess.CalledProcessError:
        print('nm -C {} failed.'.format(file_name))
    except OSError:
        print('no usable "nm" found, cannot continue')
        raise
    return symlist


def extract_symbols_from_raw_list(rs):
    '''
    Saves the entire symbol names as a single long string
    so we can say something like:
        if symbol in symbol_list
    '''
    parsed_list = []
    for sym in rs:
        sym_name = subprocess.check_output(['c++filt', sym])
        assert sym_name, 'c++filt didn\'t demangle {}'.format(sym)
        parsed_list.append(sym_name)
    return ''.join(parsed_list)


SOInfo = namedtuple('SOInfo', ['fullname', 'symbols', 'start', 'end', 'loaded'])


def load_so_list():
    '''
    Loads the list of shared libraries and returns a dictionary
    '''
    solist = gdb.execute('info sharedlibrary', to_string=True)
    solibre = r'0x([0-9a-f]+)\s+0x([0-9a-f]+).+ ([^\0]+)\/(.+)'
    solibc = re.compile(solibre)
    sodict = {}
    for so in solist.splitlines():
        m = solibc.match(so)
        if m:
            name = m.group(4)
            so_path = m.group(3)
            sa = m.group(1)
            ea = m.group(2)
            if name not in sodict:
                sodict[name] = SOInfo(
                    fullname=so_path + '/' + name,
                    symbols={},
                    start=sa,
                    end=ea,
                    loaded=False
                    )
            else:
                # this shouldn't happen but we can just verify it is indeed the same library
                assert sodict[name].start == sa, 'found same' \
                    ' library ({}) at 2 different locations: {} != {}' \
                    .format(name, sa, sodict[name].start)
                assert sodict[name].end == ea, 'found same library' \
                    ' ({}) ending at 2 different locations: {} != {}' \
                    .format(name, ea, sodict[name].end)
    return sodict


class LoadLazySymbols(gdb.Command):
    '''
    A command to load a recording without loading
    the symbols and then loading only the required symbols.
    '''

    def __init__(self):
        super(LoadLazySymbols, self).__init__('loadlazy', gdb.COMMAND_DATA, gdb.COMPLETE_FILENAME)
        self.rec = None

    def invoke(self, rec, from_tty):
        if rec == self.rec:
            pass
        else:
            self.rec = rec
            gdb.execute('set auto-solib-add off', to_string=True)
            gdb.execute('uload {}'.format(rec))


def get_frame_name(pc):
    sodict = load_so_list()
    loaded = False
    for name in sodict:
        sa = int(sodict[name].start, 16)
        ea = int(sodict[name].end, 16)
        if pc >= sa and pc < ea:
            gdb.execute('sharedlibrary {}'.format(name))
            loaded = True
    return loaded


class PopulateBT(gdb.Command):
    '''
    A command to read the symbols for an empty backtrace
    '''

    def __init__(self):
        super(PopulateBT, self).__init__('popbt', gdb.COMPLETE_EXPRESSION)

    @staticmethod
    def invoke(arg, from_tty):
        curr_frame = gdb.newest_frame()
        frames_loaded = False
        while curr_frame:
            try:
                # iteratively go through all frames and for each one check if the name is loaded.
                # if not load the name
                if not curr_frame.name():
                    frames_loaded = get_frame_name(curr_frame.pc())
                curr_frame = curr_frame.older()
            except gdb.error:
                # restart as loading frames might change things ;)
                if not frames_loaded:
                    # Didn't load anything last time, let's break as we might be
                    # in an infinite loop.
                    break
                else:
                    frames_loaded = False
                curr_frame = gdb.newest_frame()


class ReverseStepSymbol(gdb.Command):
    '''
    A command to perform reverse-step after having loaded the symbols for the target pc
    '''

    def __init__(self):
        super(ReverseStepSymbol, self).__init__('rss', gdb.COMPLETE_EXPRESSION)

    @staticmethod
    def invoke(arg, from_tty):
        gdb.execute('rsi', to_string=True)  # hide the output
        # code to resolve the symbol at pc address
        curr_frame = gdb.newest_frame()
        if not curr_frame.name():
            loaded = get_frame_name(curr_frame.pc())
            if not loaded:
                print('ERROR: shared library not found for address {:x}'.format(curr_frame.pc()))
        curr_frame = gdb.newest_frame()
        # check symbol is now present
        if not curr_frame.name():
            print('WARNING: reverse step may be slow, no symbol found for PC {:x}'
                  .format(curr_frame.pc()))
        gdb.execute('si', to_string=True)  # hide the output
        time_gdb_execute('rs')
        gdb.execute('bt 1')


class LoadLibFromSym(gdb.Command):
    '''
    Command to load all libs that might define symbol
    '''

    def __init__(self):
        super(LoadLibFromSym, self).__init__('loadsymlib', gdb.COMPLETE_EXPRESSION)
        self.sodict = {}

    def check_lib_for_symbol(self, so, symbol):
        fn = self.sodict[so].fullname
        rs = parse_raw_symlist(extract_symbol_list_from_so(fn))
        match = False
        for sym in rs:
            if symbol in sym:
                print('Got a match: {} contains {}'.format(sym, symbol))
                match = True
        if match:
            ns = six.moves.input('load library [y]/n ? ') or 'y'
            if ns != 'n':
                gdb.execute('sharedlibrary {}'.format(so))

    def load_libs_with_name(self, symbol):
        for so in self.sodict:
            self.check_lib_for_symbol(so, symbol)

    def invoke(self, symbol, from_tty):
        if not self.sodict:
            self.sodict = load_so_list()
        self.load_libs_with_name(symbol)


def time_gdb_execute(cmd):
    old_time = datetime.datetime.now()
    gdb.execute(cmd)
    new_time = datetime.datetime.now()
    delta = new_time - old_time
    if PROFILING:
        print('Duration: {} command: {}'.format(delta.total_seconds(), cmd))


LoadLibFromSym()
LoadLazySymbols()
PopulateBT()
ReverseStepSymbol()
