"""
Output utilities for the explain module.
"""

from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.udbpy import textutil
from src.udbpy.termstyles import Color, Intensity, ansi_format


@dataclass
class ToolCall:
    """
    A context manager representing an individual call to a debugger tool.

    Enter the context manager before the tool call itself is used. This class will report the call
    on the console, add results to it when provided, then display a section divider after the
    context has been exited.
    """

    tool: str
    hypothesis: str
    args: dict[str, Any]

    def __enter__(self) -> ToolCall:
        self._generate()
        return self

    def __exit__(self, *args) -> None:
        print_divider()

    def _generate(self) -> None:
        print_report_field("Tool", self.tool)
        args_fmt = ", ".join(f"{k}={v}" for k, v in self.args.items())
        if args_fmt:
            print_report_field("Arguments", args_fmt)
        print_report_field("Thoughts", self.hypothesis)

    def report_result(self, results: str) -> None:
        """
        Report a tool call result from within the context manager.
        """
        if results is None:
            results = ""

        if len(results.splitlines()) == 1:
            result_text = results
        else:
            result_text = "\n" + textwrap.indent(results, "   $  ", predicate=lambda _: True)

        print_report_field("Result", result_text)


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


def print_agent(display_name: str, agent_bin: Path) -> None:
    """
    Print agent details at startup.
    """
    print_divider()
    print_report_field("AI Agent", display_name)
    print_report_field("Agent Path", str(agent_bin))
    print_divider()


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


def print_tool_call(tool: str, hypothesis: str, args: dict[str, Any]) -> ToolCall:
    """
    Display the details of a tool call.

    Returns a context manager that can later be used to report the result of this call.
    """
    return ToolCall(tool, hypothesis, args)


def print_assistant_message(text: str) -> None:
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


def print_explanation(text: str) -> None:
    console_whizz(" * Explanation:")
    print(textwrap.indent(text, "   =  ", predicate=lambda _: True))
