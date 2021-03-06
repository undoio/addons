"""
Save and restore bookmarks to and from a file.
Usage:
    To save current bookmarks to a file:
    ubooksave <filename>
    To restore bookmarks from a file:
    ubook restore bookmarks

Contributors: Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
"""

import re
import gdb

from undodb.debugger_extensions import (
    RecordingTime,
    debugger_utils,
    udb,
)


class BookmarksSave(gdb.Command):
    def __init__(self):
        super().__init__("ubooksave", gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        with open(arg, "w") as f:
            f.write(debugger_utils.execute_to_string("uinfo bookmarks"))


bookmark_pattern = re.compile(r"""    ([0-9,]+):0x([0-9a-f]+): (.*)""")


class BookmarksRestore(gdb.Command):
    def __init__(self):
        super().__init__("ubookrestore", gdb.COMMAND_USER)

    @staticmethod
    def invoke(arg, from_tty):
        with udb.time.auto_reverting():
            with open(arg) as f:
                for bookmark in f:
                    match = bookmark_pattern.match(bookmark)
                    if match is not None:
                        bbcount = int(match.group(1).replace(",", ""))
                        pc = int(match.group(2), 16)
                        name = match.group(3)
                        udb.time.goto(RecordingTime(bbcount, pc))
                        debugger_utils.execute_to_string(f'ubookmark "{name}"')


BookmarksSave()
BookmarksRestore()
