"""
Enhanced prompt support for UDB.
Contributors: Mark Williamson, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
"""

import re
import datetime
import gdb

from undodb.debugger_extensions import (
    debugger_utils,
    udb,
)


# Configuration variable: apply colour to output?  Disable for TUI mode.
colour_enabled = False


class PromptColour(gdb.Command):
    """
    Set color on or off for enhanced UDB prompt.

    Usage: prompt-color SETTING

    Arguments:
        SETTING - on|off to enable / disable colors.
    """

    def __init__(self):
        super().__init__("prompt-color", gdb.COMMAND_SUPPORT)

    @staticmethod
    def invoke(argument, from_tty):
        global colour_enabled
        if argument == "on":
            colour_enabled = True
        elif argument == "off":
            colour_enabled = False
        else:
            raise ValueError


PromptColour()


def undodb_get_extent():
    """
    Get the event log extent of the current debuggee.

    Returns: (bb_start, bb_end) tuple of start and end bbcounts.
    """
    undodb_state = undodb_get_state()
    if undodb_state in (STATE_DEFER, STATE_NONE):
        return None
    return udb.get_event_log_extent()


STATE_NONE = "not running"
STATE_DEFER = "deferred"
STATE_RECORD = "record"
STATE_REPLAY = "replay"

RE_MODE_NOT_DEBUGGING = re.compile(r"(udb: )?(UDB|UndoDB) is not debugging an application")
RE_MODE_RECORD = re.compile(r"(udb: )?(UDB|UndoDB) is in record mode")
RE_MODE_REPLAY = re.compile(r"(udb: )?(UDB|UndoDB) is in replay mode")
RE_MODE_REPLAY_LOADED = re.compile("(udb: )?(UDB|UndoDB) is replaying a loaded recording")
RE_MODE_DEFERRED = re.compile(r"(udb: )?(UDB|UndoDB) is in deferred-recording mode")


def undodb_get_state():
    """
    Get the current debuggee state.

    Returns: A constant "STATE_" value, indicating the current state.
    Potential values are:
    * STATE_NONE   -- no debuggee running
    * STATE_DEFER  -- debuggee running with deferred recording
    * STATE_RECORD -- debuggee running in record mode
    * STATE_REPLAY -- debuggee running in replay mode
    """
    # If we get here, there's an inferior.  Check whether we're using deferred
    # recording.
    mode = debugger_utils.execute_to_string("uinfo execution-mode")

    if RE_MODE_NOT_DEBUGGING.match(mode):
        return STATE_NONE
    elif RE_MODE_RECORD.match(mode):
        return STATE_RECORD
    elif RE_MODE_REPLAY.match(mode) or RE_MODE_REPLAY_LOADED.match(mode):
        return STATE_REPLAY
    elif RE_MODE_DEFERRED.match(mode):
        return STATE_DEFER

    raise RuntimeError(f"Cannot get debuggee state. Dont know about {mode}")


def undodb_get_time():
    """
    Get the current UDB debuggee time.

    Returns: Tuple of (bbcount, pc), or None if no time is available.
    """
    undodb_state = undodb_get_state()
    if undodb_state in (STATE_DEFER, STATE_NONE):
        return None

    return udb.time.get()


TERM_BRIGHT_WHITE = "\\[\033[1m\\]"
TERM_BRIGHT_YELLOW = "\\[\033[1;33m\\]"
TERM_BRIGHT_GREEN = "\\[\033[1;32m\\]"
TERM_BRIGHT_RED = "\\[\033[1;31m\\]"
TERM_BRIGHT_BLUE = "\\[\033[1;34m\\]"
TERM_MAGENTA = "\\[\033[35m\\]"
TERM_CYAN = "\\[\033[36m\\]"
TERM_RESET = "\\[\033[m\\]"


def term_colour(c, msg):
    """
    Apply terminal colour codes to a string, if enabled.
    """
    if colour_enabled:
        return c + msg + TERM_RESET
    else:
        return msg


def prompt_state():
    """
    Return a formatted string indicating the current debuggee state.
    """
    state = undodb_get_state()
    if state == STATE_NONE:
        return term_colour(TERM_BRIGHT_WHITE, "[ nil]")
    if state == STATE_DEFER:
        return term_colour(TERM_BRIGHT_YELLOW, "[-dfr]")
    elif state == STATE_REPLAY:
        return term_colour(TERM_BRIGHT_GREEN, "[>rpl]")
    else:
        return term_colour(TERM_BRIGHT_RED, "[*rec]")


def prompt_time():
    """
    Return a formatted string indicating the current wall-clock time.
    """
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    return term_colour(TERM_BRIGHT_BLUE, "[" + time_str + "]")


def prompt_progress():
    """
    Return a formatted string indicating percentage through history.
    """
    extent = undodb_get_extent()
    if extent is None:
        return term_colour(TERM_CYAN, "[---%]")
    bb_start, bb_end = extent
    extent_time = bb_end - bb_start
    if extent_time == 0:
        return term_colour(TERM_CYAN, "[0%]")
    bb_now = undodb_get_time().bbcount
    perc = 100 * float(bb_now - bb_start) / extent_time
    return term_colour(TERM_CYAN, f"[{perc:3.0f}%]")


def prompt_bbcount():
    """
    Return a formatted string indicating the current debuggee time.
    """
    t = undodb_get_time()
    bbcount_str = str(t.bbcount) if t is not None else "?"
    return term_colour(TERM_MAGENTA, "@" + bbcount_str)


def prompt_hook(current_prompt):
    """
    Generate a new prompt string and set it as current.
    """
    prompt_components = [prompt_time, prompt_state, prompt_progress, prompt_bbcount]

    # Generate our extra prompt components.
    prompt_extra = " ".join(fn() for fn in prompt_components)

    # Interpolate extra components into our base prompt string.
    return "(udb {}) ".format(gdb.prompt.substitute_prompt(prompt_extra))


# Set GDB to call our hook before each display of the prompt.
gdb.prompt_hook = prompt_hook
