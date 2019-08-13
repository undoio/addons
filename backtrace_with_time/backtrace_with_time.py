'''
Annotates backtrace with time (basic block counts).
   Usage: ubt
'''


import gdb
from undodb.debugger_extensions import udb


class BacktraceWithTime(gdb.Command):
    def __init__(self):
        super(BacktraceWithTime, self).__init__("ubt", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):

        # Get current time, so we can go back to it afterwards.
        original_time = udb.time.get()

        # Disable all breakpoints, so we can reverse up the stack without
        # hitting anything we shouldn't.
        breakpoints = gdb.breakpoints()
        if breakpoints != None:
            for bp in breakpoints:
                bp.enabled = False
        # Get the whole backtrace.
        backtrace = gdb.execute("where", to_string=True)
        backtrace = backtrace.splitlines()

        for line in backtrace:
            # Print time at start of each backtrace line.
            time = udb.time.get()
            print '[{}]\t{}'.format(str(time.bbcount), line)
            try:
                # Go back to previous frame
                gdb.execute("rf", to_string=True)
            except:
                # Can't figure out any further - perhaps stack frame is
                # not available, or we have reached the start.
                break

        # Go back to original time.
        udb.time.goto(original_time)

        # Finally, re enable breakpoints.
        if breakpoints != None:
            for bp in breakpoints:
                bp.enabled = True


BacktraceWithTime()
