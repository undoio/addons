"""
Reconstruct the content of a socket communication by going through all events
that used the file descriptor associated to the socket.

To use, load this file in UDB (see the `source` command).

See `help extended-evt-log` for usage information.

Contributors: Emiliano Testa


TODO:
    1 - Add tests for what is present
    2 - refactor the code to remove the boilerplate / have a central place for key names
    3 - Add lots more syscalls (all the ones that use a fd)
    4 - Think of a way to have a "stream" for syscalls WITHOUT a fd
"""

import argparse
import json
#import re
import sys
import textwrap
#from enum import Enum
from pathlib import Path
from typing import Iterator, NoReturn, Optional

import gdb
import pdb
from undodb.debugger_extensions import  debugger_utils, udb#,debugger_io


def iterate_events(condition: str) -> Iterator[None]:
    """
    Stops at all events matching `condition`.

    See `ugo event next`.
    """
    while True:
        event_next_output = debugger_utils.execute_to_string(f"ugo event next {condition}")
        if "No matching event" in event_next_output:
            break
        yield


def get_syscall_argument(index: int) -> gdb.Value:
    """
    Returns a :class:`gdb.Value` representing an argument to a syscall.

    If `index` is 0 the first argument is returned, and so on.

    Execution must be stopped at a `syscall` instruction so all registers are set up for the
    syscall.
    """
    syscall_args = ["rdi", "rsi", "rdx", "r10", "r8", "r9"]
    reg_name = syscall_args[index]
    return gdb.selected_frame().read_register(reg_name)


def get_syscall_name() -> str:
    """
    Returns the name of the syscall being executed at the current time.

    Only the few syscalls required by this file as currently supported.

    Execution must be stopped at a `syscall` instruction so all registers are set up for the
    syscall.
    """
    syscall_number = int(gdb.selected_frame().read_register("eax"))
    try:
        return {
            0: "read",
            1: "write",
            2: "open",
            3: "close",
            17: "pread64",
            18: "pwrite64",
            41: "socket",
            43: "accept",
            44: "sendto",
            45: "recvfrom",
            46: "sendmsg",
            47: "recvmsg",
            49: "bind",
            50: "listen",
            257: "openat",
            299: "recvmmsg",
            307: "sendmmsg",
        }[syscall_number]
    except KeyError as exc:
        raise gdb.GdbError(f"Encountered unknown syscall {syscall_number}.") from exc

def read_memory(address: gdb.Value, size: int) -> str:
    inferior = gdb.selected_inferior()
    mem = inferior.read_memory(address, size).tobytes()
    return ''.join('{:02x}'.format(b) for b in mem)

def get_syscall_result() -> gdb.Value:
    """
    Returns the result of a syscall being executed at the current time.

    To do so, execution is moved to just after the syscall returns.

    Execution must be stopped at a `syscall` instruction.
    """
    debugger_utils.execute_to_string("nexti")
    return gdb.selected_frame().read_register("eax")

class RebuildSocketComms(gdb.Command):
    """
    Command which rebuilds all socket communications performed by a debugged program from execution
    history.

    See `help rebuid-comms` for details on usage.
    """

    def __init__(self) -> None:
        name = "extended-evt-log"

        # Force the width to fit of help messages to fit in 80 columns to match GDB's behaviour.
        class HelpFormatter(argparse.HelpFormatter):
            def __init__(self, prog, indent_increment=2, max_help_position=24, width=80):
                super().__init__(prog, indent_increment, max_help_position, width)

        super().__init__(name, gdb.COMMAND_USER)
        self.parser = argparse.ArgumentParser(
            prog=name,
            # Do not add support for -h / --help. The user can use the help command.
            add_help=False,
            formatter_class=HelpFormatter,
            description="""
                Reconstruct all socket communications performed by the target program by examining
                its execution history.
                """,
        )

        # argparse.ArgumentParser.exit calls sys.exit which, inside GDB, causes the inferior to
        # be detached.
        # We redefine the function to behave the same, except that a SystemExit is raised instead.
        # This won't be needed in Python 3.9 where the exit_on_error=False parameter can be set
        # when initialising the parser.
        def fake_exit(status: int = 0, message: Optional[str] = None) -> NoReturn:
            if message is not None:
                print(message, file=sys.stderr)
            raise SystemExit(status)

        self.parser.exit = fake_exit  # type: ignore

        self.setup_evt_dict()
        self.stream_cnt = 0
        self.stream_storage = {}
        self.char_p = gdb.lookup_type("char").pointer()
        selection_group = self.parser.add_mutually_exclusive_group()
        selection_group.add_argument(
            "-regex",
            dest="path_pattern",
            metavar="PATH-REGEX",
            default=".*",
            help="""
                A regular expression matching the path of the file to reconstruct.
                Only the first file matching the regular expression is considered.
                """,
        )
        selection_group.add_argument(
            "-fd",
            metavar="FILE-DESCRIPTOR",
            type=int,
            help="""
                The file descriptor of the file to reconstruct.
                """,
        )
        self.parser.add_argument(
            "-from-start",
            action="store_true",
            help="""
                By default, the file is reconstructed starting at the current time in execution
                history.
                With this flag, the execution history is considered from its beginning.
                """,
        )
        self.parser.add_argument(
            "-output",
            "-o",
            metavar="OUTPUT-PATH",
            help="""
                Path to a file were to write the reconstructed file.
                If not specified, the content is printed on standard output.
                """,
        )

        self.__doc__ = (
            self.parser.format_help()
            + textwrap.dedent(
                """\

            Limitations:
            - Only 64-bit x86 is supported.
            - Only files which are read in their entirety can be fully reconstructed.
            - Seeks in files being read are ignored. If the target program uses fseek or
              similar, then the file won't be reconstructed correctly.
            - Regular expressions matching the whole path (including directories) may
              not match opened files correctly due to path manipulation in the target
              program.
            - Signals may cause the command to fail in unexpected ways.
            """
            ).rstrip()
        )

    def get_stream_for_fd(self, fd: int, remove_from_count: bool = False) -> str:
        for s_name, s_fd in self.stream_storage.items():
            if fd == s_fd:
                if remove_from_count:
                    del self.stream_storage[s_name]
                return s_name
        s_name = f'stream_{self.stream_cnt}'
        self.stream_cnt += 1
        self.stream_storage[s_name] = fd
        return s_name

    def setup_evt_dict(self):
        self.evt_dict = {}
        self.evt_dict["title"] = "Extended event log"
        self.evt_dict["description"] = "Allows easier parsing of events from recordings"
        self.evt_dict["streams"] = {}

    def handle_write(self, write_type: str) -> None:
        # advance to the "syscall" instruction
        fd = int(get_syscall_argument(0))
        data_address = get_syscall_argument(1).cast(self.char_p)
        data_len = int(get_syscall_argument(2))
        write_op = {}
        write_op["type"] = write_type
        if 'pwrite' in write_type:
            write_op["offset"] = int(get_syscall_argument(3))
        current_time = udb.time.get().bbcount
        result = int(get_syscall_result())
        if result > 0:
            write_op["data"] = read_memory(data_address, result)
        else:
            write_op["data"] = 0
        write_op["data_size"] = data_len
        write_op["result"] = result
        write_op["bbcount"] = current_time
        s_name = self.get_stream_for_fd(fd)
        try:
            file_stream = self.evt_dict["streams"][s_name]
        except KeyError:
            file_stream = {
                    "file_name": "",
                    "writes": []
            }
        try:
            file_stream["writes"].append(write_op)
        except KeyError:
            file_stream["writes"] = [write_op]
        self.evt_dict["streams"][s_name] = file_stream

    def handle_read(self, read_type: str) -> None:
        # advance to the "syscall" instruction
        fd = int(get_syscall_argument(0))
        data_address = get_syscall_argument(1).cast(self.char_p)
        data_len = int(get_syscall_argument(2))
        read_op = {}
        if 'pread' in read_type:
            read_op["offset"] = int(get_syscall_argument(3))
        current_time = udb.time.get().bbcount
        result = int(get_syscall_result())
        read_op["type"] = read_type
        if result > 0:
            read_op["data"] = read_memory(data_address, result)
        else:
            read_op["data"] = 0
        read_op["data_size"] = data_len
        read_op["result"] = result
        read_op["bbcount"] = current_time
        s_name = self.get_stream_for_fd(fd)
        try:
            file_stream = self.evt_dict["streams"][s_name]
        except KeyError:
            file_stream = {
                    "file_name": "",
                    "reads": []
            }
        try:
            file_stream["reads"].append(read_op)
        except KeyError:
            file_stream["reads"] = [read_op]
        self.evt_dict["streams"][s_name] = file_stream

    def handle_close(self, syscall_name: str) -> None:
        fd = int(get_syscall_argument(0))
        current_time = udb.time.get().bbcount
        s_name = self.get_stream_for_fd(fd, remove_from_count=True)
        result = int(get_syscall_result())
        try:
            file_stream = self.evt_dict["streams"][s_name]
            file_stream["close"] = {
                "fd": fd,
                "result": result,
                "bbcount": current_time
            }
        except KeyError:
            file_stream = {
                    "file_name": "",
                    "close": {
                        "fd": fd,
                        "result": result,
                        "bbcount": current_time
                    }
            }
        self.evt_dict["streams"][s_name] = file_stream

    def handle_open(self, syscall_name: str) -> None:
        fname_idx = 0
        if syscall_name == 'openat':
            fname_idx = 1
        fname = get_syscall_argument(fname_idx).cast(self.char_p).string()
        current_time = udb.time.get().bbcount
        fd = int(get_syscall_result())
        file_stream = {
            "file_name": fname,
            syscall_name: {
                "result": fd,
                "bbcount": current_time
            }
        }
        s_name = self.get_stream_for_fd(fd)
        self.evt_dict["streams"][s_name] = file_stream

    def invoke(self, args: str, from_tty: bool) -> None:
        try:
            opts = self.parser.parse_args(gdb.string_to_argv(args))
        except SystemExit:
            # TODO: once we depend on Python 3.9, use exit_on_error=False when initialising the
            # parser rather than catching this exception.
            return

        with debugger_utils.breakpoints_suspended(), udb.time.auto_reverting():
            udb.time.goto_start()
            for _ in iterate_events("name in ('write', 'pwrite64', 'open', 'openat', 'close', 'read', 'pread64')"):
                syscall_name = get_syscall_name()
                pdb.set_trace()
                if 'write' in syscall_name:
                    self.handle_write(syscall_name)
                elif 'open' in syscall_name:
                    self.handle_open(syscall_name)
                elif syscall_name == 'close':
                    self.handle_close(syscall_name)
                elif 'read' in syscall_name:
                    self.handle_read(syscall_name)

            print(f"{opts.output=}")
            if opts.output:
                try:
                    with Path(opts.output).open('w') as json_file:
                        json.dump(self.evt_dict, json_file, indent=4)
                except IOError as exc:
                    raise gdb.GdbError("Cannot write output: {exc}") from exc
            else:
                print(json.dumps(self.evt_dict, indent=4))

RebuildSocketComms()
