# Load Debug Symbols

A common practice amongst customers is to produce binaries compiled with debug symbols and
then use a tool such as `objcopy` to strip it of symbols, producing a `.debug` symbol file
and a stripped binary. This stripped binary is then shipped as part of their product without
the .debug file being present.

When we produce a recording of an application that has been generated on binaries stripped
of symbols, the resulting recording file will also not contain debug symbols. In order to
retrospectively add the debug symbols to the recording, the user is required to use the
`add-symbol-file` command in udb and pass in the `.debug` file and relevant addresses for the
`.text`, `.data` and `.bss` sections. This script automates this process.

## Usage
```
load-debug-symbols PATHTOFILE
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/load_debug_symbols/load_debug_symbols.py
```

## Examples

`load-debug-symbols /foo/bar/baz.debug` : loads the debug symbols by parsing relevant sections.

Note that the argument to `load-debug-symbols` needs to be a valid debug symbol file and
present in the file system.
