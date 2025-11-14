"""
Amp agent implementation.
"""

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass
from typing import ClassVar

from src.udbpy.fileutil import mkstemp

from .agents import BaseAgent
from .assets import AMP_PROMPT, SYSTEM_PROMPT
from .output_utils import print_assistant_message


@dataclass
class AmpAgent(BaseAgent):
    """Amp agent implementation."""

    _thread_id: str | None = None
    _thread_answers: int = 0

    name: ClassVar[str] = "amp"
    program_name: ClassVar[str] = "amp"
    display_name: ClassVar[str] = "Amp"

    async def _handle_messages(self, stdout: asyncio.StreamReader) -> str:
        """
        Handle streamed messages from Amp until a final result, which is returned.

        Amp doesn't natively provide framing from its messages but we prompt to request a particular
        format, which this function handles.
        """
        result = ""
        msg: list[str] = []
        thinking = False
        answering = False
        async for line_bytes in stdout:
            line = line_bytes.decode("utf-8").rstrip()

            if self.log_level == "DEBUG":
                print("Line:", line)

            match line:
                case "<thinking>":
                    assert not thinking and not answering
                    thinking = True

                case "</thinking>":
                    assert thinking and not answering
                    thinking = False
                    print_assistant_message("\n".join(msg))
                    msg = []

                case "<answer>":
                    assert not thinking and not answering
                    answering = True

                case "</answer>":
                    assert answering and not thinking
                    answering = False
                    result = "\n".join(msg)

                case _ if thinking or answering:
                    msg.append(line)

        assert not thinking and not answering

        return result

    async def _discard_amp_answers(self, stdout: asyncio.StreamReader, count: int) -> None:
        """
        Discard previously-received answers on an Amp thread.

        When the Amp client resumes a thread it re-displays previous messages. We skip the number of
        previously-received answers here so that we can just display any new messages from the
        latest invocation.
        """
        while count and (line_bytes := await stdout.readline()):
            if line_bytes.decode("utf-8").rstrip() == "</answer>":
                count -= 1

    async def ask(self, question: str, port: int, tools: list[str]) -> str:
        """
        Pose a question to an external `amp` program, supplying access to a UDB MCP server.
        """
        if self.log_level == "DEBUG":
            print(f"Connecting Amp to MCP server on port {port}")

        # Craft an Amp config (n.b. this replaces the existing use config, it would probably be
        # better and safer to copy and adjust it).
        amp_config = {
            "amp.mcpServers": {"UDB_Server": {"type": "sse", "url": f"http://localhost:{port}/sse"}}
        }
        amp_config_fd, amp_config_path = mkstemp(prefix="amp_config", suffix=".json")
        with contextlib.closing(os.fdopen(amp_config_fd, "w")) as amp_config_file:
            json.dump(amp_config, amp_config_file)

        if not self._thread_id:
            # Start a new thread if one doesn't already exist for this debug session.
            amp_start_thread = await asyncio.create_subprocess_exec(
                str(self.agent_bin),
                "threads",
                "new",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert amp_start_thread.stdout and amp_start_thread.stderr

            stdout_bytes, stderr_bytes = await amp_start_thread.communicate()
            assert not stderr_bytes

            self._thread_id = stdout_bytes.decode("utf-8").rstrip()

        result = ""
        amp = None

        try:
            amp = await asyncio.create_subprocess_exec(
                str(self.agent_bin),
                "--settings-file",
                amp_config_path,
                "threads",
                "continue",
                self._thread_id,
                *self.additional_flags,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert amp.stdin and amp.stdout and amp.stderr

            # If Amp hasn't answered any questions yet we prepend a prompt to the question.
            if not self._thread_answers:
                prompt = "\n".join([AMP_PROMPT, SYSTEM_PROMPT, question])
            else:
                prompt = question

            amp.stdin.write(prompt.encode("utf-8"))
            await amp.stdin.drain()
            amp.stdin.close()

            # Throw away previous answers on this thread.
            await self._discard_amp_answers(amp.stdout, self._thread_answers)

            # Get the latest answer.
            result = await self._handle_messages(amp.stdout)
            if result:
                # Record that we've got another answer to strip.
                self._thread_answers += 1

            stderr_bytes = await amp.stderr.read()

        finally:
            if amp and amp.returncode is None:
                amp.terminate()
                await amp.wait()

            if amp and amp.returncode and stderr_bytes:
                print("Errors:\n", stderr_bytes.decode("utf-8"))

        return result
