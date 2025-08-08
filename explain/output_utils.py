"""
Output utilities for the explain module.
"""

from __future__ import annotations

import contextlib
import sys
import time
import unittest.mock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.file_proxy import FileProxy
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from src.udbpy.termstyles import Color, Intensity, ansi_format

console = Console(force_terminal=True)


class ExplainPanel(Panel):
    """
    Convenience class for displaying a panel with nice default behaviour.
    """

    def __init__(self, renderable, *args, title: str | None = None, **kwargs) -> None:
        if title:
            kwargs["title"] = f"[bold green]{title}"
            kwargs["title_align"] = "left"
        super().__init__(Padding(renderable, (0, 3)), *args, **kwargs)


@dataclass
class ToolCall:
    """
    A context manager representing an individual call to a debugger tool.

    Enter the context manager before the tool call itself is used. This class will report the call
    on the console, add results to it when provided and complete the record on the console when the
    context is exited.
    """

    tool: str
    hypothesis: str
    args: dict[str, Any]
    result: str | None = field(init=False, default=None)
    exit_stack: contextlib.ExitStack | None = field(init=False, default=None)

    def __enter__(self) -> ToolCall:
        # Don't allow a ToolCall context to be reused.
        assert self.exit_stack is None
        self.exit_stack = contextlib.ExitStack()

        live = Live(self._generate(), auto_refresh=False, console=console)
        self.exit_stack.enter_context(live)
        live.refresh()
        self.exit_stack.callback(lambda: live.update(self._generate(), refresh=True))

        # Now revert the Live class's changes to sys.stdout for the duration of
        # the tool call this context wraps. This is required for us to reliably
        # capture tool output and we will not perform any user output in the
        # interim.
        assert isinstance(sys.stdout, FileProxy)
        self.exit_stack.enter_context(
            # Pylint doesn't understand sys.stdout being a FileProxy.
            # pylint: disable=no-member
            unittest.mock.patch("sys.stdout", sys.stdout.rich_proxied_file)
        )

        return self

    def __exit__(self, *args: Any) -> None:
        assert self.exit_stack is not None
        self.exit_stack.close()

    def _generate(self) -> ExplainPanel:
        box = Table.grid()
        box.add_column("Items")

        table = Table.grid()
        table.add_column("Field", width=15, style="bold white")
        table.add_column("Value")

        table.add_row("Operation:", self.tool)
        args_fmt = ", ".join(f"{k}={v}" for k, v in self.args.items())
        if args_fmt:
            table.add_row("Arguments:", args_fmt)
        table.add_row("Thoughts:", self.hypothesis)

        box.add_row(table)

        if self.result is None:
            box.add_row(Padding("[blue italic]Processing...", (1, 0)))
        else:
            if len(self.result.splitlines()) == 1 and len(self.result) < console.size[0]:
                table.add_row("Result:", escape(self.result))
            elif self.result:
                box.add_row("[bold white]Result:")
                box.add_row(Padding(escape(self.result), (0, 3)))

        return ExplainPanel(box, title="Debugger call")

    def report_result(self, result: str) -> None:
        self.result = result


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


def print_agent(display_name: str, agent_bin: Path, style: str | None) -> None:
    """
    Print agent details at startup.
    """
    table = Table.grid()
    table.add_column("Field", width=15, style="bold white")
    table.add_column("Value")
    table.add_row("AI Agent:", display_name)
    table.add_row("Agent Path:", str(agent_bin))
    if style:
        table.add_row("Style:", style)
    console.print(ExplainPanel(table))


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
    # Truncate to 8 lines maximum of assistant output.
    lines = text.splitlines()
    if len(lines) > 8:
        lines = lines[:8] + ["", "[...]"]
    text = "\n".join(lines)

    console.print(ExplainPanel(Markdown(text), title="Assistant"))


def print_explanation(text: str) -> None:
    console_whizz(" * Explanation:")
    console.print(Padding(Markdown(text), (1, 3)))
