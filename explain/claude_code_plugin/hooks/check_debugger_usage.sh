#!/bin/bash
#
# Block direct invocation of `udb`, `live-record`, `undo`, or opening `.undo` files.
# These should only be used via the plugin's MCP tools.

set -euo pipefail

# Check if `jq` is available; if not, skip checks and allow the command.
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Read JSON input from stdin.
input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // ""')

# Block direct `udb` invocation.
if echo "$command" | grep -qE '\budb\b'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Use the /debug command or MCP debugging tools instead of invoking udb directly."}}'
    exit 0
fi

# Block direct `live-record` invocation (including architecture-specific variants like `live-record_x64`).
if echo "$command" | grep -qE '\blive-record(_[a-z0-9]+)?\b'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Use the /record command or the record MCP tool instead of invoking live-record directly."}}'
    exit 0
fi

# Block direct access to `.undo` recording files (check before `undo` to get the right message).
if echo "$command" | grep -qE '\.undo\b'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Do not access Undo recordings directly. Use the /debug command or MCP debugging tools."}}'
    exit 0
fi

# Block direct `undo` invocation.
if echo "$command" | grep -qE '\bundo\b'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Use the plugin commands (/debug, /record) or MCP tools instead of invoking undo directly."}}'
    exit 0
fi

# Allow other commands.
exit 0
