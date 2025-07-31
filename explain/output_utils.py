"""
Output utilities for the explain module.
"""

import textwrap
import time

from src.udbpy import textutil
from src.udbpy.termstyles import Color, Intensity, ansi_format


def console_whizz(msg: str, end: str = "\n") -> None:
    """
    Animated console display for major headings.
    """
    for c in msg:
        print(
            ansi_format(c, foreground=Color.GREEN, intensity=Intensity.BOLD),
            end="",
            flush=True,
        )
        time.sleep(0.01)
    print(end=end)


def print_report_field(label: str, msg: str) -> None:
    """
    Formatted field label for reporting command results.
    """
    label_fmt = ansi_format(f"{label + ':':10s}", foreground=Color.WHITE, intensity=Intensity.BOLD)
    print(f" | {label_fmt} {msg}")


def print_divider() -> None:
    """
    Display a divider between output elements.
    """
    print(" |---")


def print_assistant_message(text: str):
    """
    Display a formatted message from the code assistant.
    """
    field = "Assistant"
    # Effective width = terminal width - length of formatted field - additional chars
    single_line_width = textutil.TERMINAL_WIDTH - 14
    if len(text.splitlines()) > 1 or len(text) >= single_line_width:
        prefix = "   >  "
        # If we wrap, we'll start a new line and the width available is different.
        wrapping_width = textutil.TERMINAL_WIDTH - len(prefix)
        text = "\n".join(
            textwrap.wrap(
                text,
                width=wrapping_width,
                drop_whitespace=False,
                replace_whitespace=False,
            )
        )
        text = "\n" + textwrap.indent(text, prefix=prefix, predicate=lambda _: True)
    print_report_field(field, text)
    print_divider()
