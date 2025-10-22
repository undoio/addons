import gdb

before_prompt: gdb.EventRegistry
breakpoint_created: gdb.EventRegistry
breakpoint_modified: gdb.EventRegistry
breakpoint_deleted: gdb.EventRegistry
connection_removed: gdb.EventRegistry
cont: gdb.EventRegistry
exited: gdb.EventRegistry
gdb_exiting: gdb.EventRegistry
inferior_call: gdb.EventRegistry
inferior_deleted: gdb.EventRegistry
new_inferior: gdb.EventRegistry
new_objfile: gdb.EventRegistry
new_thread: gdb.EventRegistry
stop: gdb.EventRegistry

# Added by us.
before_stop: gdb.EventRegistry
