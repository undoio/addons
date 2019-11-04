from __future__ import absolute_import
import re
from subprocess import Popen, PIPE
import gdb


def parse_raw_symlist(syml):
    symre = r' ([^ ]*)$'
    symc = re.compile(symre)
    pl = []
    for line in syml.split('\n'):
        m = symc.search(line)
        if m:
            pl.append(m.group(1))
    return pl


def extract_symbols_from_raw_list(rs):
    '''
    Saves the entire symbol names as a single long string
    so we can say something like:
        if symbol in symbol_list
    '''
    pl = ''
    for sym in rs:
        filth = Popen(['c++filt', sym], stdout=PIPE)
        (sym_name, err) = filth.communicate()
        assert not err, 'c++filt failed {}'.format(err)
        assert sym_name, 'c++filt didn\'t demangle {}'.format(sym)
        ec = filth.wait()
        assert not ec, 'c++filt exited with {}'.format(ec)
        pl += sym_name
    return pl


class LoadLazySymbols(gdb.Command):
    '''
    A command to load a recording without loading
    the symbols and then loading only the required symbols.
    '''

    def __init__(self):
        super(LoadLazySymbols, self).__init__('loadlazy', gdb.COMPLETE_EXPRESSION)
        self.solist = []
        self.sodict = {}

    def load_so_list(self):
        self.solist = gdb.execute('info sharedlibrary', to_string=True)
        solibre = r'0x([0-9a-f]+)\s+0x([0-9a-f]+).+ ([^\0]+)\/(.+)'
        solibc = re.compile(solibre)
        for so in self.solist.split('\n'):
            m = solibc.match(so)
            if m:
                name = m.group(4)
                so_path = m.group(3)
                sa = m.group(1)
                ea = m.group(2)
                if name not in self.sodict:
                    self.sodict[name] = {}
                    self.sodict[name]['symbols'] = {}
                    self.sodict[name]['fullname'] = so_path + '/' + name
                    self.sodict[name]['start'] = sa
                    self.sodict[name]['end'] = ea
                    self.sodict[name]['loaded'] = False
                else:
                    # this shouldn't happen but we can just verify it is indeed the same library
                    assert self.sodict[name]['start'] == sa, 'found same' \
                        ' library ({}) at 2 different locations: {} != {}' \
                        .format(name, sa, self.sodict[name]['start'])
                    assert self.sodict[name]['end'] == ea, 'found same library' \
                        ' ({}) ending at 2 different locations: {} != {}' \
                        .format(name, ea, self.sodict[name]['end'])
        return self.sodict

    def load_all_symbols(self):
        for so in self.sodict:
            fn = self.sodict[so]['fullname']
            nm = Popen(['nm', '-D', fn], stdout=PIPE)
            (symlist, err) = nm.communicate()
            assert not err, 'nm failed somehow {}'.format(err)
            assert symlist, 'no symbols in file {}'.format(fn)
            ec = nm.wait()
            assert not ec, 'nm exited with {}'.format(ec)
            self.sodict[so]['symbols'] = symlist

    def invoke(self, rec, from_tty):
        if self.sodict:
            pass
        else:
            gdb.execute('set auto-solib-add off', to_string=True)
            gdb.execute('uload {}'.format(rec))


class PopulateBT(gdb.Command):
    '''
    A command to read the symbols for an empty backtrace
    '''

    def __init__(self):
        super(PopulateBT, self).__init__('popbt', gdb.COMPLETE_EXPRESSION)
        self.sodict = {}

    def get_frame_name(self, pc):
        for name in self.sodict:
            sa = int(self.sodict[name]['start'], 16)
            ea = int(self.sodict[name]['end'], 16)
            if pc >= sa and pc < ea:
                gdb.execute('sharedlibrary {}'.format(name))

    def invoke(self, arg, from_tty):
        ll = LoadLazySymbols()
        self.sodict = ll.load_so_list()
        curr_frame = gdb.newest_frame()
        while curr_frame:
            try:
                # iteratively go through all frames and for each one check if the name is loaded.
                # if not load the name
                if not curr_frame.name():
                    self.get_frame_name(curr_frame.pc())
                curr_frame = curr_frame.older()
            except gdb.error:
                # restart as loading frames might change things ;)
                curr_frame = gdb.newest_frame()
        self.sodict = {}


class LoadLibFromSym(gdb.Command):
    '''
    Command to load all libs that might define symbol
    '''

    def __init__(self):
        super(LoadLibFromSym, self).__init__('loadsymlib', gdb.COMPLETE_EXPRESSION)
        self.sodict = {}

    def read_lib_symbols(self, so):
        fn = self.sodict[so]['fullname']
        nm = Popen(['nm', '-D', fn], stdout=PIPE)
        (symlist, err) = nm.communicate()
        assert not err, 'nm failed somehow {}'.format(err)
        assert symlist, 'no symbols in file {}'.format(fn)
        ec = nm.wait()
        assert not ec, 'nm exited with {}'.format(ec)
        rs = parse_raw_symlist(symlist)
        self.sodict[so]['symbols'] = extract_symbols_from_raw_list(rs)

    def find_lib_with_symbol(self, symbol):
        for so in self.sodict:
            if not self.sodict[so]['loaded']:
                if not self.sodict[so]['symbols']:
                    self.read_lib_symbols(so)
                if symbol in self.sodict[so]['symbols']:
                    self.sodict[so]['loaded'] = True
                    return so
        return None

    def load_libs_with_name(self, symbol):
        match = self.find_lib_with_symbol(symbol)
        assert match, 'didn\'t find a library with symbol {}'.format(symbol)
        gdb.execute('sharedlibrary {}'.format(match))

    def invoke(self, symbol, from_tty):
        if not self.sodict:
            ll = LoadLazySymbols()
            self.sodict = ll.load_so_list()
        self.load_libs_with_name(symbol)


LoadLibFromSym()
LoadLazySymbols()
PopulateBT()
