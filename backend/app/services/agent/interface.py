"""
AutoHeal DevOps — Infrastructure Agent Interface
Abstract contract for communicating with restricted infrastructure execution agents.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.services.agent.models import (
    ActionRequest,
    ActionResult,
    AgentHeartbeat,
    AgentRegistration,
)


class InfrastructureAgentClient(ABC):
    """
    Abstract base class for infrastructure agents.
    Defines methods for action dispatch, cancellation, status polling, and registration.
    """

    @abstractmethod
    async def register(self, registration: AgentRegistration) -> bool:
        """Registers the agent with the control plane."""
        pass

    @abstractmethod
    async def get_heartbeat(self) -> AgentHeartbeat:
        """Queries the current health and workload metrics of the agent node."""
        pass

    @abstractmethod
    async def dispatch_action(self, request: ActionRequest) -> ActionResult:
        """
        Dispatches a cryptographically signed, allowlisted action envelope to the agent.
        Blocks or polls until completion or timeout, returning the verified ActionResult.
        """
        pass

    @abstractmethod
    async def cancel_action(self, action_id: str) -> bool:
        """Signals the agent to terminate an in-flight operation."""
        pass
