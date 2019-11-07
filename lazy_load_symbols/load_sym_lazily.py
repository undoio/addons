from __future__ import absolute_import

import re
import subprocess
from subprocess import Popen, PIPE
import datetime
import random
from collections import namedtuple
import traceback

import gdb


def parse_raw_symlist(syml):
    symre = r' ([^ ]*)$'
    symc = re.compile(symre)
    for line in syml.split('\n'):
        m = symc.search(line)
        if m:
            yield(m.group(1))


def extract_symbol_list_from_so(file_name):
    try:
        symlist = subprocess.check_output(['nm', '-C', file_name])
    except subprocess.CalledProcessError:
        print('nm -C {} failed'.format(file_name))
        raise
    except OSError:
        print('no usable "nm" found, cannot continue')
        raise
    assert symlist, 'no symbols in file {}'.format(file_name)
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
                    fullname = so_path + '/' + name,
                    symbols = {},
                    start = sa,
                    end = ea,
                    loaded = False
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
        self.sodict = {}
        self.rec = None


    def load_all_symbols(self):
        for content in self.sodict.values():
            fn = content.fullname
            content.symbols = extract_symbol_list_from_so(fn)

    def invoke(self, rec, from_tty):
        try:
            if self.sodict and \
               rec == self.rec:
                pass
            else:
                self.rec = rec
                gdb.execute('set auto-solib-add off', to_string=True)
                gdb.execute('uload {}'.format(rec))
        except Exception:
            traceback.print_exc()

class PopulateBT(gdb.Command):
    '''
    A command to read the symbols for an empty backtrace
    '''

    def __init__(self):
        super(PopulateBT, self).__init__('popbt', gdb.COMPLETE_EXPRESSION)

    def get_frame_name(pc):
        sodict = load_so_list()
        for name in sodict:
            sa = int(sodict[name].start, 16)
            ea = int(sodict[name].end, 16)
            if pc >= sa and pc < ea:
                gdb.execute('sharedlibrary {}'.format(name))

    def invoke(self, arg, from_tty):
        curr_frame = gdb.newest_frame()
        frames_loaded = False
        while curr_frame:
            try:
                # iteratively go through all frames and for each one check if the name is loaded.
                # if not load the name
                if not curr_frame.name():
                    self.get_frame_name(curr_frame.pc())
                    frames_loaded = True
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
    A command to find reverse step and find symbols for the current program counter
    '''

    def __init__(self):
        super(ReverseStepSymbol, self).__init__('rss', gdb.COMPLETE_EXPRESSION)

    def get_frame_name(self, pc):
        sodict = load_so_list()
        loaded = False
        try:
            for name in sodict:
                sa = int(sodict[name].start, 16)
                ea = int(sodict[name].end, 16)
                if pc >= sa and pc < ea:
                    gdb.execute('sharedlibrary {}'.format(name))
                    print('found sharedlibrary', name)
                    loaded = True
            if not loaded:
                print 'ERROR: shared library not found for address {pc}'
        except gdb.error as e:
            print('ERROR: gdb eror', e)

    def invoke(self, arg, from_tty):
        #gdb.execute('bt 1')
        gdb.execute('rsi', to_string=True)  # hide the output
        #gdb.execute('bt 1')
        # code to resolve the symbol at pc address
        curr_frame = gdb.newest_frame()
        print(curr_frame, "PC", curr_frame.pc(), "name", curr_frame.name())
        if not curr_frame.name():
            self.get_frame_name(curr_frame.pc())
        try:
            curr_frame = gdb.newest_frame()
            print(curr_frame.name())
        except gdb.error as e:
            print('ERROR:', e)
        # check symbol is now present
        hex_pc = hex(curr_frame.pc())
        if not curr_frame.name():
            print('WARNING: reverse step may be slow, no symbol found for PC {}'.format(hex_pc))
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

    def read_lib_symbols(self, so):
        fn = self.sodict[so].fullname
        rs = parse_raw_symlist(extract_symbol_list_from_so(fn))
        self.sodict[so]._replace(symbols = extract_symbols_from_raw_list(rs))

    def find_lib_with_symbol(self, symbol):
        for so, content in self.sodict.items():
            if not content.loaded:
                if not content.symbols:
                    self.read_lib_symbols(so)
                if symbol in content.symbols:
                    content.loaded = True
                    return so
        return None

    def load_libs_with_name(self, symbol):
        match = self.find_lib_with_symbol(symbol)
        assert match, 'didn\'t find a library with symbol {}'.format(symbol)
        gdb.execute('sharedlibrary {}'.format(match))

    def invoke(self, symbol, from_tty):
        try:
            if not self.sodict:
                self.sodict = load_so_list()
            self.load_libs_with_name(symbol)
        except Exception:
            traceback.print_exc()

def time_gdb_execute(cmd):
    old_time = datetime.datetime.now()
    gdb.execute(cmd)
    new_time = datetime.datetime.now()
    delta = new_time - old_time
    print("Duration:", delta.total_seconds(), "command:", cmd)

def ugo_random():
    endre = r'.*in recorded range: .*- ([0-9,]+)\].*'
    endc = re.compile(endre)
    uinfo_time = gdb.execute('uinfo time', to_string=True)
    m = endc.match(uinfo_time)
    end_bb = m.group(1)
    end_bb = end_bb.replace(',', '')
    random_bb = random.randint(1, long(end_bb))
    cmd = 'ugo time {}'.format(random_bb)
    print(cmd)
    time_gdb_execute(cmd)

LoadLibFromSym()
LoadLazySymbols()
PopulateBT()
ReverseStepSymbol()
