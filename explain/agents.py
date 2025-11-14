"""
Agent registry system for AI coding assistants.
"""

from __future__ import annotations

import os
import shlex
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class BaseAgent(ABC):
    """Base interface for AI coding assistants."""

    agent_bin: Path
    log_level: str = "CRITICAL"
    additional_flags: list[str] = field(default_factory=list)

    name: ClassVar[str]
    program_name: ClassVar[str]
    display_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Subclasses must set up their identifying strings.
        required = ["name", "program_name", "display_name"]
        if not all(hasattr(cls, f) for f in required):
            raise ValueError(
                f"Agent class {cls.__name__} must define non-empty attributes: {','.join(required)}"
            )

        AgentRegistry.agents[cls.name] = cls

    @classmethod
    def find_binary(cls) -> Path | None:
        """
        Find and return the path to the agent binary.

        Returns:
            Path to the agent binary, or None if not found
        """
        if loc := shutil.which(cls.program_name):
            return Path(loc)
        else:
            return None

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


class AgentRegistry:
    """Registry for managing available AI agents."""

    agents: dict[str, BaseAgent] = {}

    @classmethod
    def available_agents(cls) -> list[str]:
        """Get a list of all registered agent names."""
        return list(cls.agents.keys())

    @classmethod
    def _create_if_available(
        cls, agent_class: Any, log_level: str, additional_flags: list[str]
    ) -> BaseAgent | None:
        """
        Create an instance of the agent if it's available on the system.

        Args:
            agent_class: The agent class (subclass of BaseAgent) to instantiate
            log_level: Log level to pass to the agent
            additional_flags: Additional command-line flags to pass to the agent

        Returns:
            Agent instance if available, None otherwise
        """
        binary = agent_class.find_binary()
        if binary:
            return agent_class(binary, log_level=log_level, additional_flags=additional_flags)
        return None

    @classmethod
    def select_agent(
        cls, preferred_name: str | None = None, log_level: str = "CRITICAL"
    ) -> BaseAgent:
        """
        Select an agent, preferring the specified one or auto-selecting.

        Args:
            preferred_name: Preferred agent name, or None for auto-selection
            log_level: Log level to pass to the agent

        Returns:
            Selected agent instance

        Raises:
            Exception: If no agents are available or preferred agent is not found
        """
        # Parse additional flags from environment variable
        additional_flags = []
        if flags_str := os.environ.get("EXPLAIN_AGENT_FLAGS"):
            additional_flags = shlex.split(flags_str)

        # Get instances of all available agents on the system
        available = {}
        for name, agent_class in cls.agents.items():
            instance = cls._create_if_available(
                agent_class, log_level=log_level, additional_flags=additional_flags
            )
            if instance:
                available[name] = instance

        if not available:
            raise Exception("Could not find any installed coding agents.")

        # Check command line argument first, then environment variable
        agent_name = preferred_name or os.environ.get("EXPLAIN_AGENT")
        if agent_name:
            if agent_name in available:
                return available[agent_name]

            # Handle unavailable agent
            source = "command line" if preferred_name else "EXPLAIN_AGENT environment variable"
            raise Exception(
                f"Agent {agent_name!r} from {source} is not available. "
                f"Available agents: {','.join(available.keys())}"
            )

        # Auto-select: prefer Claude Code, then others
        if "claude" in available:
            return available["claude"]

        # Return the first available agent
        return next(iter(available.values()))
