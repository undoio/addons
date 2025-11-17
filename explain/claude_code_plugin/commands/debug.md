# Debug Undo Recording

Help the user debug a program using an Undo recording.

## IMPORTANT: Do not open recordings directly

Undo recordings are opaque binary files. You MUST NOT try to open, read, or parse recording files directly. If you see a `.undo` file, always use the MCP tools to investigate it.

## Recording Path

Arguments provided: `$ARGUMENTS`

If the user mentioned a recording file (which will appear in $ARGUMENTS), use that path.

If no recording path was provided:
- Search for .undo files in the current directory
- Check previous messages in the conversation
- Ask the user for the recording path

## What to do

Use the available MCP tools from the `undo-debugger` MCP server to investigate the recording.

The MCP server instructions provide comprehensive guidance on reverse debugging techniques.
Common starting points:
- Use `backtrace` to understand the current program state
- Use `last_value` to trace how variables were set
- Use `ubookmark` to mark interesting points in time
- Use time-travel debugging to work backwards from the failure

Trust the tool docstrings and the MCP instructions to guide your debugging approach.
