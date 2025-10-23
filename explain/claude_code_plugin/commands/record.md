# Record Program Execution

Create an Undo recording of a program execution using `live-record`.

## Arguments

Arguments provided: `$ARGUMENTS`

## What to do

1. **Extract the command to record** from the user's message or $ARGUMENTS
   - If unclear, ask: "What is the full command you want to record (including any arguments)?"

2. **Determine the recording path**
   - If the user specifies a path, use it
   - Otherwise, suggest a sensible default based on the program name (e.g., `./my_program.undo`)

3. **Call the MCP tool**
   - `record(command="./program arg1 arg2", recording="./program.undo")`
   - Or with a list: `record(command=["./program", "arg1", "arg2"], recording="./program.undo")`

## Example

**User:** "Record ./my_app --verbose"
**You do:** Call `record(command="./my_app --verbose", recording="./my_app.undo")`

The tool will handle execution and provide guidance on next steps. After successful recording, the user can use `/undo:debug` to analyze it.
