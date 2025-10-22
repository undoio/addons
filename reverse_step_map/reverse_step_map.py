import re
import sys
from pathlib import Path

import gdb
from undo.debugger_extensions import debugger_utils


what_map_dir = Path(__file__).parent.parent / "what_map"
assert what_map_dir.is_dir(), f"Not a directory {what_map_dir}"
sys.path.append(str(what_map_dir))
import what_map as _


class ReverseStepMapCommand(gdb.Command):
    """
    Step backward one instruction and print the registers and maps used in that instruction.
    Usage: rsm
    """

    # Regex for common 64-bit registers in x86_64 assembly (AT&T syntax).
    REGISTER_REGEX = re.compile(r"(?:\*?(?P<offset>-?0x[0-9a-f]+)\()?%\b(?P<reg>[a-z0-9]{2,8})\b")

    def __init__(self) -> None:
        super().__init__("reverse-step-maps", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        # 1. Reverse-single-step one instruction
        debugger_utils.execute_to_string("rsi")

        # 2. Get the current instruction text at $pc
        disasm_line = debugger_utils.execute_to_string("x/i $pc")
        # Example line: "=> 0x5555555550e9 <main+9>:	mov    rax, QWORD PTR [rbp-0x8]"

        # Strip off address and arrow, keep only the instruction part
        # Split at the first colon, take the second piece
        try:
            _, instr_text = disasm_line.split(":", 1)
        except ValueError as exc:
            raise gdb.GdbError(f"Could not parse instruction at $pc: {disasm_line!r}") from exc
        instr_text = instr_text.strip()  # e.g. "mov    rax, QWORD PTR [rbp-0x8]"
        print("Instruction:", instr_text)

        # 3. Find all register occurrences (roughly matched)
        regs_used = set(re.findall(self.REGISTER_REGEX, instr_text))

        # 4. Print the updated values of these registers
        #    The parse_and_eval("$rax") style references GDB's notion of registers.
        for r in regs_used:
            try:
                offset = 0
                if isinstance(r, tuple):
                    if r[0]:
                        offset = int(r[0], 16)
                    reg = r[1]
                else:
                    reg = r
                val = gdb.parse_and_eval(f"${reg}")
                # Convert to Python int for printing in hex/dec
                val_int = int(val) & 0xFFFFFFFFFFFFFFFF  # ensure 64-bit wrap if needed
                val_int += offset
                print(f"{reg} + {offset:#x} = {val_int:#016x} ({val_int})")
                gdb.execute(f"whatmap *{val_int:#016x}")
            except gdb.error as exc:
                # Some registers or partial registers may not parse in all architectures
                raise gdb.GdbError(f"{reg} is not available or failed to parse.") from exc


# Register our command when the script is loaded
ReverseStepMapCommand()
