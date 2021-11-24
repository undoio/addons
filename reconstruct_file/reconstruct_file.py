"""
Reconstruct the content of files by analysing reads in the execution history of a debugged program
or LiveRecorder recording.

To use, load this file in UDB (see the `source` command).

See `help reconstruct-file` for usage information.

Contributors: Marco Barisione
"""

import argparse
import re
import sys
import textwrap
from pathlib import Path
from typing import Iterator, NoReturn, Optional

import gdb

from undodb.debugger_extensions import debugger_io, debugger_utils, udb


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
            2: "open",
            3: "close",
            257: "openat",
        }[syscall_number]
    except KeyError as exc:
        raise gdb.GdbError(f"Encountered unknown syscall {syscall_number}.") from exc


def get_syscall_result() -> gdb.Value:
    """
    Returns the result of a syscall being executed at the current time.

    To do so, execution is moved to just after the syscall returns.

    Execution must be stopped at a `syscall` instruction.
    """
    debugger_utils.execute_to_string("nexti")
    return gdb.selected_frame().read_register("eax")


def find_open(path_pattern: str) -> Optional[int]:
    """
    Searches in recorded history for a syscall opening a file whose name matches (with
    :func:`re.search`) the regular expression in `path_pattern`.

    Returns the file descriptor for the file, or `None` if not found.
    """
    char_ptr_type = gdb.lookup_type("char").pointer()

    for _ in iterate_events("name in ('openat', 'open')"):
        syscall_name = get_syscall_name()
        if syscall_name == "openat":
            # Argument 0 is dirfd while argument 1 is the path (absolute or relative).
            # See openat(2).
            path_argument_index = 1
        elif syscall_name == "open":
            # Argument 0 is the path. See open(2).
            path_argument_index = 0
        else:
            raise gdb.GdbError(f"Unexpected syscall {syscall_name} encountered")

        pathname = get_syscall_argument(path_argument_index).cast(char_ptr_type).string()
        if re.search(path_pattern, pathname) is not None:
            return int(get_syscall_result())

    return None


def get_reads_content(fd: int) -> bytes:
    """
    Searches in recorded history for all writes to `fd` and returns the content that was read from
    that file (until end of history or until the file is closed).
    """
    content = bytearray()
    seen_any_read = False
    unsigned_char_p = gdb.lookup_type("unsigned char").pointer()

    for _ in iterate_events("name in ('close', 'read')"):
        syscall_name = get_syscall_name()
        # Both close and read accept the fd as first argument, see close(2) and read(2).
        actual_fd = int(get_syscall_argument(0))
        if actual_fd != fd:
            # Not for the file we are interested in.
            continue

        if syscall_name == "read":
            seen_any_read = True
            # The return value is the number of bytes read.
            n_read = int(get_syscall_result())
            # The second argument is a buffer where the syscall wrote n_read bytes.
            buff_p = get_syscall_argument(1).cast(unsigned_char_p)
            # gdb.Value.string (with length set to n_read) can convert the buffer to a Python
            # string, but we need to deal with non-Unicode content which is not supported directly
            # by gdb.Value. Instead, we convert one byte at a time.
            for i in range(n_read):
                char_value = int(buff_p[i])
                content.append(char_value)

        elif syscall_name == "close":
            # The file is being closed so there are not going to be further reads.
            break

        else:
            raise gdb.GdbError(f"Unexpected syscall {syscall_name} encountered")

    if not seen_any_read:
        raise gdb.GdbError(f"Cannot find any read from file descriptor {fd}.")

    return bytes(content)


class ReconstructFile(gdb.Command):
    """
    Command which reconstructs the conent of a file read by a debugged program from execution
    history.

    See `help reconstruct-file` for details on usage.
    """

    def __init__(self) -> None:
        name = "reconstruct-file"

        # Force the width to fit of help messages to fit in 80 columns to match GDB's behaviour.
        class HelpFormatter(argparse.HelpFormatter):
            def __init__(self, prog, indent_increment=2, max_help_position=24, width=80):
                super().__init__(prog, indent_increment, max_help_position, width)

        self.parser = argparse.ArgumentParser(
            prog=name,
            # Do not add support for -h / --help. The user can use the help command.
            add_help=False,
            formatter_class=HelpFormatter,
            description="""
                Reconstruct a file read by the target program by examining its execution history.

                Use the -regex or -fd options to select which file to reconstruct or, if omitted,
                the first file opened is reconstructed.
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

        super().__init__(name, gdb.COMMAND_USER)

    def invoke(self, args: str, from_tty: bool) -> None:
        try:
            opts = self.parser.parse_args(gdb.string_to_argv(args))
        except SystemExit:
            # TODO: once we depend on Python 3.9, use exit_on_error=False when initialising the
            # parser rather than catching this exception.
            return

        try:
            gdb.selected_frame()
        except gdb.error as exc:
            raise gdb.GdbError("The program is not being run.") from exc
        if gdb.selected_inferior().architecture().name() != "i386:x86-64":
            raise gdb.GdbError("Only 64-bit x86 is supported.")

        with debugger_utils.suspend_breakpoints(), udb.time.auto_reverting():
            if opts.from_start:
                with debugger_io.RedirectOutput("/dev/null"):
                    udb.time.goto_start()

            if opts.fd is None:
                opts.fd = find_open(opts.path_pattern)
                if opts.fd is None:
                    raise gdb.GdbError(
                        f"Cannot find any call to open a file matching {opts.path_pattern!r}."
                    )

            content = get_reads_content(opts.fd)
            if opts.output:
                try:
                    Path(opts.output).write_bytes(content)
                except IOError as exc:
                    raise gdb.GdbError("Cannot write output: {exc}") from exc
            else:
                print(content.decode(errors="backslashreplace").replace("\0", "\\x00"))


ReconstructFile()
