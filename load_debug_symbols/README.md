Load Debug Symbols
==================

Loads a debug symbol file at the right addresses for .text, .data and .bss sections.

Usage: load-debug-symbols PATHTOFILE

Examples:
load-debug-symbols /foo/bar/baz.debug - Loads the debug symbols by parsing relevant sections.

Note that the argument to "load-debug-symbols" needs to be a valid debug symbol file and
present in the file system.
