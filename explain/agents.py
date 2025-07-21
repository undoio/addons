"""
Base agent interface for AI coding assistants.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BaseAgent(ABC):
    """Base interface for AI coding assistants."""

    agent_bin: Path
    log_level: str = "CRITICAL"

    @abstractmethod
    async def ask(self, question: str, port: int, tools: list[str]) -> str:
        """
        Ask the agent a question with access to MCP tools.

        Args:
            question: The question to ask
            port: Port of the MCP server
            tools: List of available tools

        Returns:
            The agent's response
        """
