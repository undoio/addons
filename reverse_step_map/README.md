# Reverse step maps

This command helps with finding quickly which maps each instruction works on.

Currently this script works only on x86 assembly, not ARM.

Other limitations include:

- not able to calculate the right address with certain addressing modes, for example:
  (%rax, %rbx, 8)
- not able to parse xmm* registers: gdb.parse_and_eval() returns an error on such registers.

## Requirements

This command requires another addons command to be present too: `whatmap`

## Installation

To install this script you only need to source it in udb:

```
source waht_map/what_map.py
source reverse_step_map/reverse_step_map.py
```

## Usage

simply type `rsm` and you should get output similar to:

```
99% 15,486,248> rsm
Instruction: movq   $0x0,0x18dd32(%rip)        # 0x772dcc41ca58 <list_all_lock+8>
rip + 18dd32 = 0x0000772dcc41ca4d (131038584097357)
Searching maps for address 0x772dcc41ca4d:
          0x772dcc41c000     0x772dcc41d000     0x1000        0x0  rw-p
```

