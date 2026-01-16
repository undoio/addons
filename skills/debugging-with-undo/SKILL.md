---
name: debugging-with-undo
description: >
  Debug programs using Undo time travel debugging. Record flaky tests, intermittent failures,
  race conditions, or bugs that don't reproduce reliably. Analyze recordings by traveling
  backwards through execution history. Use when the user mentions debugging, flaky tests,
  intermittent bugs, race conditions, `.undo` files (Undo recordings), or asks why something
  happened in an actual run. This can provide similar results as adding logging statements,
  but without modifying the code or needing to re-run the program multiple times.
---

# Debugging with Undo time travel debugger

Undo provides time travel debugging for Linux programs. This Skill guides you to:
1. **Record** program execution to capture failures (especially intermittent ones)
2. **Debug** recordings by traveling backwards through execution history

## When to record (use `record` MCP tool)

Record program execution when the user:
- Has a **flaky test** or **intermittent failure** that doesn't reproduce reliably
- Mentions **race conditions**, **threading issues**, or **concurrency bugs**
- Wants to **capture a failure** for later analysis
- Needs **deterministic replay** of a bug

Undo captures the exact execution including thread interleavings, making even race conditions
reproducible.

## When to debug (use debugging MCP tools)

Debug a recording when the user:
- Has a **`.undo` recording file** to investigate
- Asks **"why did this happen"** or **"how did this value get set"**
- Wants **root cause analysis** on a captured failure
- Needs to understand execution **backwards** from a crash or assertion

## Workflow

1. **If no recording exists**: Use `record` MCP tool to capture the failure
2. **If recording exists**: Use debugging MCP tools to analyze it
3. **Work backwards**: Start at the end (where the bug manifested), trace backwards

## Important

- **Never access `.undo` files directly** - they are opaque binary recordings
- **Never invoke `udb`, `live-record`, or `undo` via Bash** - use the Undo MCP tools
