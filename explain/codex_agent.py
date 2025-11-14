"""
Codex agent implementation.
"""

import asyncio
import json
import sys
import textwrap
from dataclasses import dataclass
from itertools import chain, repeat
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

    _session_id: str | None = None

    async def _handle_messages(self, stdout: asyncio.StreamReader) -> str:
        """
        Handle streamed messages from Codex until a final result, which is returned.
        """
        result = ""
        async for line in stdout:
            line_data = json.loads(line)
            if self.log_level == "DEBUG":
                print("Message:", line_data)

            match line_data:
                case {"type": "turn.completed"}:
                    # We're done.
                    break
                case {"type": "item.completed", "item": item}:
                    # Extract the "item" member from completed items.
                    pass
                case {"type": "thread.started", "thread_id": session_id}:
                    # Fetch the session ID so messages are a part of the same conversation.
                    self._session_id = session_id
                    continue
                case _:
                    # For any other message, just keep going.
                    continue

            # React to a completed "item".
            match item:
                case {"type": "reasoning", "text": text}:
                    # Report the reasoning, if this codex feature is turned on.
                    print_assistant_message(text)
                case {"type": "agent_message", "text": result}:
                    # Agent messages are added to the end of the run, whose result is returned.
                    # https://github.com/openai/codex/blob/main/docs/exec.md#json-output-mode
                    print_assistant_message(result)
                case {"type": "command_execution", "command": command}:
                    # Report the execution of non-Undo tools. For now, we don't report the result.
                    print_assistant_message(command)
                case _:
                    continue

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
                *(["resume", self._session_id] if self._session_id else []),
                *self.additional_flags,
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

        if not result:
            result = textwrap.dedent(
                """\
                Could not parse the response.
                Try upgrading your codex application to the latest version.
                """
            )

        return result
