"""
Claude Code agent implementation.
"""

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from src.udbpy.fileutil import mkstemp

from .agents import BaseAgent
from .assets import SYSTEM_PROMPT
from .output_utils import print_assistant_message


@dataclass
class ClaudeAgent(BaseAgent):
    """Claude Code agent implementation."""

    _session_id: str | None = None

    name: ClassVar[str] = "claude"
    program_name: ClassVar[str] = "claude"
    display_name: ClassVar[str] = "Claude Code"

    @classmethod
    def find_binary(cls) -> Path | None:
        """
        Find and return the path to the Claude binary.

        Returns:
            Path to the Claude binary, or None if not found
        """
        claude_local_install_path = Path.home() / ".claude" / "local" / cls.program_name

        if loc := super().find_binary():
            return loc
        elif claude_local_install_path.exists():
            return claude_local_install_path

        return None

    async def _handle_messages(self, stdout: asyncio.StreamReader) -> str:
        """
        Handle streamed JSON messages from Claude until a final result, which is returned.
        """
        result = ""

        async for line in stdout:
            msg = json.loads(line)
            if self.log_level == "DEBUG":
                print("Claude:", msg)

            if msg.get("type") == "result":
                # Fetch the session ID so that we can resume our conversation next time.
                self._session_id = msg["session_id"]

                # Stash the result so that we can print our overall explanation.
                result = msg["result"]

                # This should be the last message in the stream, allow us to fall out of the loop
                # naturally and return it.
                continue

            if msg.get("type") != "assistant":
                # We only need to report things the code assistant did.
                continue

            # Gather relevant content for display (if any).
            content = msg.get("message").get("content", [])
            display_content = []
            for c in content:
                match c:
                    case {"type": "text", "text": text}:
                        display_content.append(text)
                    case {"type": "tool_use", "name": tool_name} if not tool_name.startswith(
                        "mcp__UDB_Server"
                    ):
                        # Report use of other tools.
                        args = "\n".join(f"    {k}='{v}'" for k, v in c.get("input").items())
                        display_content.append(f"Tool use: {tool_name}\n{args}")

            if not display_content:
                # Nothing interesting to say.
                continue

            assistant_text = "\n".join(display_content)
            # Print an interim assistant message.
            print_assistant_message(assistant_text)

        return result

    async def ask(self, question: str, port: int, tools: list[str]) -> str:
        """
        Pose a question to an external `claude` program, supplying access to a UDB MCP server.
        """
        if self.log_level == "DEBUG":
            print(f"Connecting Claude to MCP server on port {port}")

        mcp_config = {
            "mcpServers": {"UDB_Server": {"type": "sse", "url": f"http://localhost:{port}/sse"}}
        }
        mcp_config_fd, mcp_config_path = mkstemp(prefix="mcp_config", suffix=".json")
        with contextlib.closing(os.fdopen(mcp_config_fd, "w")) as mcp_config_file:
            json.dump(mcp_config, mcp_config_file)

        allowed_tools = ",".join(f"mcp__UDB_Server__{t}" for t in tools)

        result = ""
        claude = None
        try:
            claude = await asyncio.create_subprocess_exec(
                str(self.agent_bin),
                *(["--resume", self._session_id] if self._session_id else []),
                "--model",
                "opus",
                "--mcp-config",
                mcp_config_path,
                "--allowedTools",
                allowed_tools,
                "--output-format",
                "stream-json",
                "--verbose",  # Required for --output-format stream-json
                "-p",
                question,
                "--system-prompt",
                SYSTEM_PROMPT,
                *self.additional_flags,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert claude.stdout and claude.stderr

            result = await self._handle_messages(claude.stdout)

            stderr = await claude.stderr.read()
            if stderr:
                print("Errors:\n", stderr)

        finally:
            # Make sure Claude is properly cleaned up if we exited early.
            if claude and claude.returncode is None:
                claude.terminate()
                await claude.wait()

        return result
