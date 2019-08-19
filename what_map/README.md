What map
========

Looks up a variable or address within the maps of the debuggee.

Usage: whatmap EXPRESSION

Examples:  
whatmap my_variable        - Looks up the map containing the named variable.
whatmap *0x1234            - Looks up the map containing the address 0x1234.

Note that the argument to "whatmap" needs to be addressable - in other words, you should use an
argument that you would pass to "watch".

This command works with vanilla GDB or within UDB. When run under UDB it will inspect the maps
of the currently active child process - note that these don't exactly match the maps that were
present at record time.

