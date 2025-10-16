from pathlib import Path
from typing import Dict

import gdb


try:
    from elftools.elf.elffile import ELFFile
except ModuleNotFoundError:
    check_build_id = False
else:
    check_build_id = True


def create_file_dict(path: Path) -> Dict[str, Path]:
    ret_dict = {}
    for f in path.glob("**/*.debug"):
        # Remove the .debug suffix from the file name.
        ret_dict[f.name[:-6]] = f
    return ret_dict


def match_build_id(debug_file: Path, obj: gdb.Objfile) -> bool:
    if not check_build_id:
        return True
    with debug_file.open("rb") as fd:
        ef = ELFFile(fd)
        sect = ef.get_section_by_name(".note.gnu.build-id")
        # The data is a long string that contains the build-id at the end,
        # starting from index 32. Reference can be found here:
        # https://interrupt.memfault.com/blog/gnu-build-id-for-firmware
        # in hex each byte is 2 char long -> 4fields*4bytes*2char = 32
        # NOTE: We always assume that name is 4 bytes "GNU\0".
        # This is always true for GCC and Clang compiled binaries.
        debug_build_id = sect.data().hex()[32:]
    return debug_build_id == obj.build_id


class ExtraSymbolsCommand(gdb.Command):
    """
    A command to load all external symbol files for debuggee.
    Usage: allsym PATH_TO_SYMBOL_ROOT
    """

    def __init__(self) -> None:
        super().__init__("load-all-symbols", gdb.COMMAND_FILES, gdb.COMPLETE_FILENAME)

    @staticmethod
    def invoke(argument: str, from_tty: bool) -> None:
        in_path = Path(argument).expanduser()
        if not in_path.exists():
            raise gdb.GdbError("Invalid directory specified.")
        sym_dict = create_file_dict(in_path)
        for obj in gdb.objfiles():
            if obj.filename:
                leaf_name = Path(obj.filename).name
            else:
                if obj.is_valid():
                    print(f"WARNING, valid obj {obj} has no filename associated to it, skipping")
                continue
            debug_path = sym_dict.get(leaf_name)
            if debug_path is not None:
                if match_build_id(debug_path, obj):
                    print(f"Loading separate debug info for {leaf_name} from {debug_path}")
                    obj.add_separate_debug_file(str(debug_path))
                else:
                    print(
                        f"{leaf_name} has debug file: {debug_path} "
                        "with mismatching Build-ID, ignoring"
                    )
        if not check_build_id:
            print(
                "WARNING: couldn't check the Build-ID of the loaded symbols. "
                "Results might be wrong. Update your copy of UDB to get pyelftools."
            )


ExtraSymbolsCommand()
