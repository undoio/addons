# Load Debug Symbols

A common practice amongst UDB users is to produce binaries compiled with debug symbols and
then use a tool such as `objcopy` to strip it of symbols, producing a `.debug` symbol file
and a stripped binary. This stripped binary is then shipped as part of their product without
the .debug file being present.

When we produce a recording of an application that has been generated on binaries stripped
of symbols, the resulting recording file will also not contain debug symbols. In order to
retrospectively add the debug symbols to the recording, the user is required to use a rather
complex procedure to be able to load all symbols files.
This script automates the symbol loading completely.

The script will traverse the whole directory structure, the user is just asked for the base
directory.

## Usage
```
load-all-symbols PATHTOBASEDIR
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/automatic_symbol_loading/automatic_symbol_loading.py
```

## Examples

`load-all-symbols /data/mci/` : for each library loaded in UDB looks for the symbol file
(by taking into consideration all and only the files ending in `.debug`) and, if the Build-IDs
match, it loads the symbol-file.

Note that the argument to `load-debug-symbols` needs to be a valid directory. If not
the script will exit immediately.
