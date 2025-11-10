"""
Copilot CLI agent implementation.
"""

import asyncio
import itertools
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from src.udbpy.fileutil import mkdtemp

from .agents import BaseAgent
from .assets import FRAMING_PROMPT, SYSTEM_PROMPT
from .output_utils import print_assistant_message


@dataclass
class CopilotCLIAgent(BaseAgent):
    """Copilot CLI agent implementation."""

    _tempdir: Path | None = None
    _resume: bool = False

    name: ClassVar[str] = "copilot"
    program_name: ClassVar[str] = "copilot"
    display_name: ClassVar[str] = "Copilot CLI"

    async def _handle_messages(self, stdout: asyncio.StreamReader) -> str:
        """
        Handle streamed messages from Copilot until a final result, which is returned.

        Copilot doesn't natively provide framing from its messages but we prompt to request a
        particular format, which this function handles.
        """
        result = ""
        msg: list[str] = []
        thinking = False
        answering = False
        async for line_bytes in stdout:
            line = line_bytes.decode("utf-8").rstrip()

            if self.log_level == "DEBUG":
                print("Line:", line)

            if "<thinking>" in line:
                assert not thinking and not answering
                thinking = True

            elif "</thinking>" in line:
                assert thinking and not answering
                thinking = False
                print_assistant_message("\n".join(msg))
                msg = []

            elif "<answer>" in line:
                assert not thinking and not answering
                answering = True

            elif "</answer>" in line:
                assert answering and not thinking
                answering = False
                result = "\n".join(msg)

            elif thinking or answering:
                msg.append(line)

        assert not thinking and not answering

        return result

    async def ask(self, question: str, port: int, tools: list[str]) -> str:
        """
        Pose a question to an external `copilot` program, supplying access to a UDB MCP server.
        """
        if self.log_level == "DEBUG":
            print(f"Connecting Copilot CLI to MCP server on port {port}")

        copilot_config = {
            "mcpServers": {
                "UDB_Server": {"type": "sse", "url": f"http://localhost:{port}/sse", "tools": ["*"]}
            }
        }

        # We run Copilot CLI with a temporary "home directory" so that we can apply a temporary MCP
        # configuration and rely on "--resume" finding our previous session automatically.
        if not self._tempdir:
            self._tempdir = mkdtemp(prefix="udb_explain_copilot_home")

        # We always need to re-create the MCP config as the dynamically allocated port may change
        # between invocations of the tool.
        config_dir = self._tempdir / ".copilot"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "mcp-config.json").write_text(json.dumps(copilot_config) + "\n")

        result = ""
        copilot = None

        # If Copilot hasn't answered any questions yet we prepend our prompt to the question.
        if not self._resume:
            prompt = "\n".join([FRAMING_PROMPT, SYSTEM_PROMPT, question])
        else:
            prompt = question

        allowed_tools = ["UDB_Server", "shell(grep)", "shell(find)", "shell(cat)", "shell(xargs)"]
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self._tempdir),
            "XDG_STATE_HOME": str(self._tempdir),
        }

        try:
            copilot = await asyncio.create_subprocess_exec(
                str(self.agent_bin),
                # We can resume unambiguously without specifying a session ID because we're using a
                # temporary home directory for the state generated in this session.
                *(["--resume"] if self._resume else []),
                # Don't allow any tools that may write output (for now).
                "--deny-tool",
                "write",
                *itertools.chain(*[("--allow-tool", t) for t in allowed_tools]),
                "--model",
                "claude-sonnet-4.5",
                "-p",
                prompt,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert copilot.stdin and copilot.stdout and copilot.stderr

            result = await self._handle_messages(copilot.stdout)

        finally:
            if copilot and copilot.returncode is None:
                copilot.terminate()
                await copilot.wait()

            if copilot and copilot.stderr:
                stderr_bytes = await copilot.stderr.read()
                if copilot.returncode and stderr_bytes:
                    print("Errors:\n", stderr_bytes.decode("utf-8"))

        self._resume = True

        return result
