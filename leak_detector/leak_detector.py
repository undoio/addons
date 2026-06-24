"""
Find memory leaks when malloc and free are used.
Starting from the current position it matches all calls to malloc
with calls to free with the same pointer and
keeps track of the calls that have no corresponding call to free.
It is recommended to go to the start of time and then use the command.
It prints a full list of unmatched calls at the end.
    Usage: mleak

Contibutors:  Emiliano Testa
Copyright (C) 2022 Undo Ltd
"""

import copy
import gdb

from undodb.debugger_extensions import (
    udb,
)


ALLOC_FN = "malloc"
FREE_FN = "free"
all_allocs = []


class MemAlloc:
    def __init__(self, addr, size, bbcount):
        self.addr = addr
        self.size = size
        self.bbcount = bbcount


def handle_alloc_fn():
    frame = gdb.selected_frame()
    size = frame.read_register("rdi")
    bbcount = udb.time.get().bbcount
    gdb.execute("finish")
    frame = gdb.selected_frame()
    addr = frame.read_register("rax")
    all_allocs.append(MemAlloc(addr, size, bbcount))


def handle_free_fn():
    frame = gdb.selected_frame()
    addr = frame.read_register("rdi")
    for alloc in copy.copy(all_allocs):
        if alloc.addr == addr:
            all_allocs.remove(alloc)


def handle_bp_event(event):
    if hasattr(event, "breakpoints"):
        for bp in event.breakpoints:
            if bp.location == ALLOC_FN:
                handle_alloc_fn()
            elif bp.location == FREE_FN:
                handle_free_fn()


class LeakDetect(gdb.Command):
    def __init__(self):
        super().__init__("mleaks", gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        gdb.Breakpoint(ALLOC_FN)
        gdb.Breakpoint(FREE_FN)
        gdb.events.stop.connect(handle_bp_event)
        end_of_time = udb.get_event_log_extent().max_bbcount
        gdb.execute("continue")
        while udb.time.get().bbcount < end_of_time:
            gdb.execute("continue")
        print("Calls to allocator fn that don't have a corresponding free")
        for alloc in all_allocs:
            print(f"{hex(alloc.addr)} - {hex(alloc.size)} - {alloc.bbcount}")


LeakDetect()
