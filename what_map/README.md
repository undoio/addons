# What map

Looks up a variable or address within the maps of the debuggee.

## Usage
```
whatmap EXPRESSION
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/what_map/what_map.py
```

## Examples

`whatmap my_variable` : looks up the map containing the named variable.

`whatmap *0x1234` : looks up the map containing the address 0x1234.

Note that the argument to `whatmap` needs to be addressable - in other words, you should use an
argument that you would pass to `watch`.

This command works with vanilla GDB or within UDB. When run under UDB it will inspect the maps
of the currently active child process - note that these don't exactly match the maps that were
present at record time.
