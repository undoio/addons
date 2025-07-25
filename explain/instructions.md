This MCP server provides access to the UDB time travel debugger. It is a superior replacement for
the GDB debugger and adds the ability to travel backwards in time.

You should assume that operations have similar behaviour to their GDB counterparts.

# Time travel debugging

Time travel debugging provides two key abilities:

 * The ability to replay the same execution history precisely the same, repeatedly.  If the user has
   recorded their bug they do not need to restart or rebuild their application.
 * The ability to rewind execution history.  This tells the user why a given program state exists,
   not just what state exists.

To debug effectively, you should start by recording the bug.  Don't try to stop the debugger before
the bug occurs, instead you should allow the bug to be captured and then work backwards.

# Running UDB

UDB is already run under the control of the server.

## Start and end of history

If you see the message "Have reached start of recorded history." it means you've got too far back in
history.  If the user managed to record their bug this means you have stepped past it and should try
another approach.

Use `ugo_end` to skip to the end of history, before working backwards to understand the failure.

## Navigating the stack

Use `backtrace` to find out what function you are in and what called it.

Use `reverse_finish` to wind time back to before the current function was
called.  You can apply this repeatedly.

```
stack trace:
    my_leaf_function() <- current location at top
    my_middle_function()
    my_main_function()

debug tool:
    reverse_finish

stack trace:
    my_middle_function() <- current location at top
    my_main_function()
```

## The standard library

If the program stops within the standard library it is unlikely to be
interesting to the user.  You should use `reverse_finish` to step out of it and
back to user code.

## Navigating function calls

Use `reverse_next` to step backwards over a function as it is called.

```
Source context:
    10   int my_value = called_function()
 -> 11   a = a + b;

UDB:reverse_next

Source context:
     9
 -> 10 int my_value = called_function()
    11 a = a + b;
```

## Inspecting values

Use `last` to wind back time to find out how and when a value was set.

```
source lines:
    int my_value = called_function()

    ... many other lines skipped ...

    printf("My value is %d\n", my_value); <- debug location

debug tool:
    last my_value

source lines:
    int my_value = called_function() <- debug location
```

This works even when the memory location was modified a long time ago or in a
different function.

When `last` returns it specifies a "Was" value, which is what you were
investigating.  "Now" is the previous value, which should be ignored or used
for a new debugging hypothesis.

`last` will only work for values that are currently in scope.  If a value is not
currently in scope then you need to navigate backwards in time until it is.  Using
`reverse_step`, `reverse_next` and `reverse_finish` can help you work
back to when a value is in scope.

You should use `reverse_finish` if the scope of the value is another function.
If the scope of the value is the current function you can use `reverse_step`
and `reverse_next`.

If you use `last` on an argument to the current function call you might see an
invalid intermediate value as the result.  You can step backwards out of the
function and print the parameter value to check what it was really set to.

Use `print` to find out the current value of a variable.  If you have just run
`last` then printing the value of the same variable should give the same
current contents, otherwise something has gone wrong.

## Understanding `if` statements

If the user is currently in an `if` statement, step back to the condition (the
part in parentheses) and try to explain the boolean that was evaluated there.

You could step back to the condition using `reverse_next`.

If you cannot tell what the values involved in the calculation were, try to
retrieve them using the `last` command.

```
source lines:
    if (a != b) {
        calculate_further_values()

        ... skipped other lines ...

        assert(bad); <- debug location
    }

debug tool:
    reverse_next (repeat as needed)

source lines:
    if (a != b) { <- debug location
        calculate_further_values()
        ... skipped other lines ...

debug tool:
    last a OR last b (to investigate why the `if` statement was entered)
```

## Bookmarks

Set bookmarks (using `ubookmark`) at interesting points in recorded history if they may require
further investigation later or if they will form part of your final explanation of the bug.

Query bookmarks (using `info_bookmarks`) to recall interesting points in time that have previously
been identified by either you or the user.

Return to bookmarks (using `ugo_bookmark`) to begin further investigations starting from that point
in time.

Examples of useful places to add a bookmark:
 * When you have just identified where a value was set.
 * When you have just discovered a new bad value.
 * When you have just discovered when a relevant function was run.
 * When you have just stepped into an interesting function or blockof code.

When you explain a bug you should cite the names of bookmarks that are relevant to your explanation.

# Explaining a bug

To diagnose the bug follow the following procedure:

 1. Hypothesis: Form a hypothesis about why the bug occurred.  Start with getting a `backtrace`.
 2. Heuristic investigation: Select a relevant heuristic tool and follow its procedure to investigate the hypothesis.
 3. Evaluate: Determine whether the hypothesis was correct, incorrect or untestable.  Create a bookmark at this point.
 4. Report: Report your findings to the user, citing bookmarks you created where relevant.
 4a. If the bug has been root caused, report to the user.
 4b. If the bug has not been root caused, repeat from step 1 for the new hypothesis.
