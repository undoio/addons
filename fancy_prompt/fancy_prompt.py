'''
Enhanced prompt support for UndoDB.
Contributors: Mark Williamson, Toby Lloyd Davies
Copyright (C) 2019 Undo Ltd
'''

from __future__ import absolute_import, division
import re
import datetime
from undodb.debugger_extensions import udb
import gdb


# Configuration variable: apply colour to output?  Disable for TUI mode.
colour_enabled = False


class PromptColour(gdb.Command):
    '''
    Set color on or off for enhanced UndoDB prompt.

    Usage: prompt-color SETTING

    Arguments:
        SETTING - on|off to enable / disable colors.
    '''

    def __init__(self):
        super(PromptColour, self).__init__('prompt-color', gdb.COMMAND_SUPPORT)

    @staticmethod
    def invoke(argument, from_tty):
        global colour_enabled
        if argument == 'on':
            colour_enabled = True
        elif argument == 'off':
            colour_enabled = False


PromptColour()


def undodb_get_extent():
    '''
    Get the event log extent of the current debuggee.

    Returns: (bb_start, bb_end) tuple of start and end bbcounts.
    '''
    undodb_state = undodb_get_state()
    if undodb_state == STATE_DEFER or undodb_state == STATE_NONE:
        return None
    return udb.get_event_log_extent()


STATE_NONE = 'not running'
STATE_DEFER = 'deferred'
STATE_RECORD = 'record'
STATE_REPLAY = 'replay'

RE_MODE_NOT_DEBUGGING = re.compile('UndoDB is not debugging an application')
RE_MODE_RECORD = re.compile('UndoDB is in record mode')
RE_MODE_REPLAY = re.compile('UndoDB is in replay mode')
RE_MODE_REPLAY_LOADED = re.compile('UndoDB is replaying a loaded recording')
RE_MODE_DEFERRED = re.compile('UndoDB is in deferred-recording mode')


def undodb_get_state():
    '''
    Get the current debuggee state.

    Returns: A constant "STATE_" value, indicating the current state.
    Potential values are:
    * STATE_NONE   -- no debuggee running
    * STATE_DEFER  -- debuggee running with deferred recording
    * STATE_RECORD -- debuggee running in record mode
    * STATE_REPLAY -- debuggee running in replay mode
    '''
    # If we get here, there's an inferior.  Check whether we're using deferred
    # recording.
    mode = gdb.execute('uinfo execution-mode', to_string=True)

    if RE_MODE_NOT_DEBUGGING.match(mode):
        return STATE_NONE
    elif RE_MODE_RECORD.match(mode):
        return STATE_RECORD
    elif RE_MODE_REPLAY.match(mode) or RE_MODE_REPLAY_LOADED.match(mode):
        return STATE_REPLAY
    elif RE_MODE_DEFERRED.match(mode):
        return STATE_DEFER

    raise RuntimeError('dont know about {}'.format(mode))


def undodb_get_time():
    '''
    Get the current UndoDB debuggee time.

    Returns: Tuple of (bbcount, pc), or None if no time is available.
    '''
    undodb_state = undodb_get_state()
    if undodb_state == STATE_DEFER or undodb_state == STATE_NONE:
        return None

    return udb.time.get()


TERM_BRIGHT_WHITE = r'\[\033[1m\]'
TERM_BRIGHT_YELLOW = r'\[\033[1;33m\]'
TERM_BRIGHT_GREEN = r'\[\033[1;32m\]'
TERM_BRIGHT_RED = r'\[\033[1;31m\]'
TERM_BRIGHT_BLUE = r'\[\033[1;34m\]'
TERM_MAGENTA = r'\[\033[35m\]'
TERM_CYAN = r'\[\033[36m\]'
TERM_RESET = r'\[\033[m\]'


def term_colour(c, msg):
    '''
    Apply terminal colour codes to a string, if enabled.
    '''
    if colour_enabled:
        return c + msg + TERM_RESET
    else:
        return msg


def prompt_state():
    '''
    Return a formatted string indicating the current debuggee state.
    '''
    state = undodb_get_state()
    if state == STATE_NONE:
        return term_colour(TERM_BRIGHT_WHITE, '[ nil]')
    if state == STATE_DEFER:
        return term_colour(TERM_BRIGHT_YELLOW, '[-dfr]')
    elif state == STATE_REPLAY:
        return term_colour(TERM_BRIGHT_GREEN, '[>rpl]')
    else:
        return term_colour(TERM_BRIGHT_RED, '[*rec]')


def prompt_time():
    '''
    Return a formatted string indicating the current wall-clock time.
    '''
    time_str = datetime.datetime.now().strftime('%H:%M:%S')
    return term_colour(TERM_BRIGHT_BLUE, '[' + time_str + ']')


def prompt_progress():
    '''
    Return a formatted string indicating percentage through history.
    '''
    extent = undodb_get_extent()
    if extent is None:
        return term_colour(TERM_CYAN, '[---%]')
    bb_start, bb_end = extent
    bb_now = undodb_get_time().bbcount
    perc = 100 * float(bb_now - bb_start) / (bb_end - bb_start)
    return term_colour(TERM_CYAN, '[{:3.0f}%]'.format(perc))


def prompt_bbcount():
    '''
    Return a formatted string indicating the current debuggee time.
    '''
    t = undodb_get_time()
    bbcount_str = str(t.bbcount) if t is not None else '?'
    return term_colour(TERM_MAGENTA, '@' + bbcount_str)

BASE_PROMPT = '(udb %s) '

def prompt_hook(current_prompt):
    '''
    Generate a new prompt string and set it as current.
    '''
    prompt_components = [prompt_time,
                         prompt_state,
                         prompt_progress,
                         prompt_bbcount]

    # Generate our extra prompt components.
    prompt_extra = ' '.join(fn() for fn in prompt_components)

    # Interpolate extra components into our base prompt string.
    prompt = BASE_PROMPT % prompt_extra

    # Set GDB to actually use the updated prompt string.
    gdb.execute('set prompt {}'.format(gdb.prompt.substitute_prompt(prompt)))


# Set GDB to call our hook before each display of the prompt.
gdb.prompt_hook = prompt_hook