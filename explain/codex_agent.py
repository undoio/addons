"""
Codex agent implementation.
"""

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from itertools import chain, repeat
from pathlib import Path
from typing import ClassVar

from .agents import BaseAgent
from .assets import CODEX_PROMPT, SYSTEM_PROMPT
from .output_utils import print_assistant_message


@dataclass
class CodexAgent(BaseAgent):
    """Codex agent implementation."""

    name: ClassVar[str] = "codex"
    program_name: ClassVar[str] = "codex"
    display_name: ClassVar[str] = "Codex"

    @classmethod
    def find_binary(cls) -> Path | None:
        """
        Find and return the path to the Codex binary.

        Returns:
            Path to the Codex binary, or None if not found
        """
        if loc := shutil.which(cls.program_name):
            return Path(loc)
        else:
            return None

    async def _handle_messages(self, stdout: asyncio.StreamReader) -> str:
        """
        Handle streamed messages from Codex until a final result, which is returned.
        """
        result = ""
        async for line in stdout:
            line_data = json.loads(line)
            if self.log_level == "DEBUG":
                print("Message:", line_data)

            msg = line_data.get("msg")
            if not msg:
                continue

            if msg.get("type") == "task_complete":
                result = msg["last_agent_message"]
                continue

            if msg.get("type") != "agent_message":
                continue

            content = msg["message"]
            print_assistant_message(content)

            result = repr(msg)

        return result

    async def ask(self, question: str, port: int, tools: list[str]) -> str:
        """
        Pose a question to an external `codex` program, supplying access to a UDB MCP server.
        """
        if self.log_level == "DEBUG":
            print(f"Connecting Codex to MCP server on port {port}")

        # Codex requires an external mcp_proxy program to talk to a non-stdio MCP server.
        # The "explain" extension brings in that package as part of its dependencies, so we just
        # have to tell Codex how to run it.

        # Configuration details for codex.
        codex_mcp_prefix = "mcp_servers.UDB_server"
        codex_mcp_settings = {
            "command": sys.executable,
            "args": f'["-m", "mcp_proxy", "http://localhost:{port}/sse"]',
            "env": '{"PYTHONPATH" = "' + ":".join(sys.path) + '"}',
        }

        codex_config_settings = [
            f"{codex_mcp_prefix}.{key}={value}" for key, value in codex_mcp_settings.items()
        ]
        config_opts = list(chain(*zip(repeat("--config"), codex_config_settings)))

        result = ""
        stderr_bytes = b""
        codex = None

        try:
            codex = await asyncio.create_subprocess_exec(
                str(self.agent_bin),
                *config_opts,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "\n".join([SYSTEM_PROMPT, CODEX_PROMPT, question]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert codex.stdout and codex.stderr

            # Get the latest answer.
            result = await self._handle_messages(codex.stdout)

            stderr_bytes = await codex.stderr.read()

        finally:
            if codex and codex.returncode is None:
                codex.terminate()
                await codex.wait()

            if codex and codex.returncode and stderr_bytes:
                print("Errors:\n", stderr_bytes.decode("utf-8"))

        return result
