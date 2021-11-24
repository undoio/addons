import gdb

before_prompt: gdb.EventRegistry
breakpoint_created: gdb.EventRegistry
breakpoint_modified: gdb.EventRegistry
breakpoint_deleted: gdb.EventRegistry
exited: gdb.EventRegistry
inferior_call: gdb.EventRegistry
inferior_deleted: gdb.EventRegistry
new_inferior: gdb.EventRegistry
new_objfile: gdb.EventRegistry
stop: gdb.EventRegistry
