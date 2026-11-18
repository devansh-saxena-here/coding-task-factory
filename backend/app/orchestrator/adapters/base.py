"""
Base Agent Adapter Protocol — Day 11 Step 2.

Defines the abstract interface that all AI coding agent harnesses must implement.
Provides a provider-independent asynchronous execution, cancellation, and log-streaming
contract using validated orchestrator Pydantic schemas.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.schemas.orchestrator import AgentExecutionResult, AgentPromptPayload


class AgentAdapter(ABC):
    """
    Abstract interface for AI Coding Agent Adapters.
    
    Subclasses wrap concrete agent harnesses (direct LLM tool-calling APIs,
    CLI wrappers, or autonomous agents) behind a consistent asynchronous contract.
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """
        Unique machine-readable identifier for this agent adapter.
        
        Example: 'gemini-flash', 'claude-code-cli', 'mock-agent'
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable name used in dashboards and benchmark scorecards.
        """
        pass

    @abstractmethod
    async def dispatch_task(
        self,
        payload: AgentPromptPayload,
        workspace_path: str,
    ) -> AgentExecutionResult:
        """
        Dispatches the coding task to the agent and waits for workspace modification.
        
        Args:
            payload: Validated task instruction, title, file context, and timeout.
            workspace_path: Absolute or contained path to the isolated repository copy.
            
        Returns:
            AgentExecutionResult containing execution status, generated git patch,
            token telemetry, and execution logs.
            
        Raises:
            TimeoutError: If execution exceeds payload.timeout_sec.
            RuntimeError: On fatal adapter or communication failure.
        """
        pass

    @abstractmethod
    async def cancel_run(self, run_id: str) -> bool:
        """
        Attempts to cancel or abort an active agent execution.
        
        Args:
            run_id: Unique identifier of the agent run to abort.
            
        Returns:
            True if cancellation was successfully issued; False otherwise.
        """
        pass

    @abstractmethod
    def stream_logs(self, run_id: str) -> AsyncIterator[str]:
        """
        Yields real-time stdout and stderr log chunks emitted by the agent.
        
        Args:
            run_id: Unique identifier of the active agent run.
            
        Yields:
            Incremental string log messages.
        """
        pass
