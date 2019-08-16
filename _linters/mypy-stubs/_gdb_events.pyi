import gdb

before_prompt: gdb.EventRegistry
exited: gdb.EventRegistry
inferior_call: gdb.EventRegistry
inferior_deleted: gdb.EventRegistry
new_inferior: gdb.EventRegistry
new_objfile: gdb.EventRegistry
stop: gdb.EventRegistry
