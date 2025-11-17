# Configure Undo Path

Configure the path to the Undo Suite installation or UDB executable.

## Arguments

Arguments provided: `$ARGUMENTS`

## What to do

1. **Extract the path** from the user's message or $ARGUMENTS
   - If the user wants to clear the path, pass `None`
   - If unclear, ask: "What is the full path to your UDB executable or Undo installation directory?"

2. **Call the MCP tool**
   - To set: `configure_undo_path(path="/path/to/undo")`
   - To clear: `configure_undo_path(path=None)`

The tool accepts:
- Path to `udb` or `live-record` executable
- Path to Undo Suite installation directory
- `None` to clear the configuration

After successful configuration, any previously failed operations due to missing Undo tools should work.
