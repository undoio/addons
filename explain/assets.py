"""
Static text assets loaded from external files.
"""

from pathlib import Path


# Protected module global for asset file paths
_EXTENSION_PATH = Path(__file__).parent

MCP_INSTRUCTIONS = (_EXTENSION_PATH / "instructions.md").read_text(encoding="UTF-8")
"""Top-level instructions for the MCP server."""

SYSTEM_PROMPT = (_EXTENSION_PATH / "system_prompt.md").read_text(encoding="UTF-8")
"""System prompt to supply to Claude on every invocation."""

THINKING_MSGS = (_EXTENSION_PATH / "thinking.txt").read_text(encoding="UTF-8").split("\n")[:-1]
"""Messages to display whilst the system is thinking."""

FRAMING_PROMPT = (_EXTENSION_PATH / "framing_prompt.md").read_text(encoding="UTF-8")
"""Message-framing prompt for agents that don't support JSON output."""

AMP_PROMPT = FRAMING_PROMPT + (_EXTENSION_PATH / "amp_prompt.md").read_text(encoding="UTF-8")
"""Amp-specific prompt for framing responses and encouraging thorough investigation."""

CODEX_PROMPT = (_EXTENSION_PATH / "codex_prompt.md").read_text(encoding="UTF-8")
"""Codex-specific prompt to encourage thorough investigation."""
