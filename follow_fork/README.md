Follow `fork()`
===============

Often, when recording, engineers might want to record both the parent and the
children generated during the run.
This pre-load library intercepts the calls to 'fork()' and calls the
[LiveRecorder API](http://undo.io) to record the child.

Note
----

You will need to have the LiveRecorder library in order to be able to
use this utility.

Compiling
---------

In order to be able to use the library it needs to be compiled with
the following command:

```
gcc -I /<path>/<to>/<undodb-xxxx>/undolr -L /<path>/<to>/<undodb-xxxx>/undolr -shared -fPIC follow_fork.c -o libfollowfork.so -l:libundolr_pic_x64.a -std=c99 -ldl
```

In order to use the library you'll need to do the following:

```
LD_PRELOAD=<path_to>/libfollowfork.so <app to record> <args....>
```


