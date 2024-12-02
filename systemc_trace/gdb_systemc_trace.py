#!/usr/bin/env python
from __future__ import print_function
import os
import argparse
from subprocess import call

parser = argparse.ArgumentParser(description='GDB SystemC tracing')
parser.add_argument("-l", "--list_signals", help="print all signals in design without running simulation", action="store_true")
parser.add_argument("-p", "--print_hier", help="print design tree", action="store_true")
parser.add_argument("-f", "--signals_file", help="file with list of signals to trace", type=str)
parser.add_argument("-r", "--recording_file", help="Undo recording of SystemC simulation", type=str)
parser.add_argument("sim_exe", help="SystemC simulation executable", type=str, nargs="?")

args, unknownargs = parser.parse_known_args()

trace_script = (os.path.dirname(os.path.abspath(__file__)))+"/gdb_scripts/run_trace.py"

argdict = {'list_signals': args.list_signals,
           'print_hier': args.print_hier,
           'signals_file': args.signals_file,
           'recording_file': args.recording_file}
argstring = "py argdict = " + str(argdict) + ""

if args.recording_file:
    call_list = ["udb", "--sessions", "no", "--batch"]
else:
    call_list = ["gdb"]

call_list.extend(["-ex", argstring, "-ix", "~/.gdbinit", "-x", trace_script])

if args.recording_file:
    call_list.append(args.recording_file)
    assert unknownargs == []
else:
    assert args.sim_exe
    call_list.extend(["--args", args.sim_exe])
    call_list.extend(unknownargs)


call(call_list)
