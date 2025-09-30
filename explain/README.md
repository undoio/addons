Explain Extension
=================

This directory contains an [extension](https://docs.undo.io/Addons.html) that integrates AI coding
agent support into UDB, the time travel debugger of the [Undo Suite](http://undo.io/).

For the impatient: Add `explain` to your UDB session using the `extend explain` command, then get
started asking questions using the `explain` command (or via the `uexperimental mcp serve` command
if you don't have a supported CLI coding agent).

If you don't have an Undo license to test with you can download a [free
trial](https://undo.io/udb-free-trial/).

What is it?
-----------

Explain extends a time travel debugger (a debugger that can capture and query the entire history of
a program at machine-instruction precision) with the ability to ask questions about the program's
dynamic behaviour. These might be as simple as "What has gone wrong in this program?" to root cause
a crash, or more complex (and iterative) questioning to navigate the semantics of a program.

For example, you could **Debug a cache corruption** that lead to a program crash:

[![Debug a cache corruption using
AI](https://img.youtube.com/vi/p416JIurLiU/0.jpg)](https://www.youtube.com/watch?v=p416JIurLiU)

Or you could **Ask questions about a game you recorded**, using AI to navigate the semantics of the
program and its dynamic behaviour during the particular session you recorded:

[![Ask questions about a game of
Doom](https://img.youtube.com/vi/dmH7owoctC4/0.jpg)](https://www.youtube.com/watch?v=dmH7owoctC4)

For more details about `explain`, you can refer to [our
blogpost](https://undo.io/resources/time-travel-ai-code-assistant/) about it.

What can I ask it?
------------------

You can ask it anything you want about the state of the recorded program. Good questions involve
questions about the current state of the recorded program or about its overall behaviour.

> [!NOTE]
> `explain` is primarily designed for *querying* program history and the tools that it exposes to
> the AI coding agent are optimised for this. As a result it does not have access to all debugger
> functionality - it isn't designed to replace your IDE interface or the debugger's own command
> line, so requests like "set a breakpoint" are not supported.

Requirements
------------

For full integration into the UDB debugger you must install a supported, CLI-based coding
agent. This must be one of:

 * [Claude Code](https://www.anthropic.com/claude-code)
 * [Amp](https://ampcode.com/)
 * [Codex CLI](https://developers.openai.com/codex/cli/)
 * [Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli)

If the extension detects an installation of one of these it will attempt to use it to answer your
questions about the program's recorded history.

To use UDB from other coding agents, start the included MCP server and connect from your preferred
agent. To start the MCP server, use the command `uexperimental mcp serve` and configure your coding
agent to connect.

> [!CAUTION]
>
> Use of the MCP server from the command line of Undo's [Time Travel Debug for C/C++
> extension](https://marketplace.visualstudio.com/items?itemName=Undo.udb) for VS Code is currently
> not supported, this will be improved in future release.
