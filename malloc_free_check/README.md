# Memory leak detection example
This example implements a simple memory leak detector with the Undo Automation API.

The `memchecker.c` example application has a single unmatched `malloc()` call (excluding some from before the application has actually started, including the 1KB buffer for printfs, which are detected).

Using the Undo Automation API, the python scripts process the recording to find all `malloc()` and `free()` calls.  The script ignores all `malloc()` calls with matching `free()` call, and after parsing the entire recording, jumps back in time to each of the unmatched `malloc()` calls.  For each call, the scripts:
* Output the backtrace at the time of the call.
* Continue execution until `malloc()` returns.
* Outputs the souce code for the calling function (if available) and locals.

In the case of the example program, this is sufficient to clearly show the root cause for the deliberate leak.  Generally it should give a good hint for other recordings, and the output does clearly provide the timestamps for the `malloc()` calls to enable opening the recording and jumping directly to the leaking memory allocation to start debugging from there.

These scripts can be used as a starting point to implement other kinds of analysis related to the standard allocation functions, such as producing a profile of how much memory is being used during execution.

## How to run the demo
Simply enter the directory and run:

`make run`

## How to use the scripts on other recordings
Simply run the `malloc-free.py` script, passing the recording as the parameter:

`./malloc-free.py <recording.undo>`

## Enhancements ideas
* Provide some way to filter out library code.
* Add verbosity controls.
* Support recordings without symbols (provide address for `malloc()` & `free()` at command line).
* Automatically trace the use of leaking memory to identify the last read or write access to the memory.
