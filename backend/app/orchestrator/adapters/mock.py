"""
Mock Replay Adapter — Day 11 Step 3.

Provides a safe, deterministic mock implementation of the AgentAdapter protocol.
Simulates agent execution scenarios (success, failure, timeout, cancellation,
empty patch, malformed patch) and async log streaming without executing any shell
commands, Python code, patches, or external APIs on the host.

All outputs are explicitly marked as [SIMULATED].
"""

import asyncio
from typing import AsyncIterator, Literal

from app.orchestrator.adapters.base import AgentAdapter
from app.schemas.orchestrator import (
    AgentExecutionResult,
    AgentExecutionStatus,
    AgentPromptPayload,
)

MockScenarioLiteral = Literal[
    "success",
    "failure",
    "timeout",
    "cancellation",
    "empty_patch",
    "malformed_patch",
]


class MockReplayAdapter(AgentAdapter):
    """
    Deterministic simulated agent adapter for testing orchestrator workflows.
    
    IMPORTANT: Outputs from this adapter represent synthetic simulation only
    and do NOT constitute proof that an actual coding agent executed or solved a task.
    """

    def __init__(
        self,
        agent_id: str = "mock-replay-agent",
        display_name: str = "Mock Replay Agent (Simulated)",
        default_scenario: MockScenarioLiteral = "success",
    ):
        self._agent_id = agent_id
        self._display_name = display_name
        self.default_scenario = default_scenario
        self._cancelled_runs: set[str] = set()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def display_name(self) -> str:
        return self._display_name

    async def dispatch_task(
        self,
        payload: AgentPromptPayload,
        workspace_path: str,
        scenario: MockScenarioLiteral | None = None,
    ) -> AgentExecutionResult:
        """
        Simulates task execution deterministically without host code execution.
        
        Args:
            payload: Validated task prompt, instructions, and timeout ceiling.
            workspace_path: Target workspace path (inspected safely, never executed).
            scenario: Optional scenario override (success, failure, timeout, etc.).
            
        Returns:
            Validated AgentExecutionResult matching the chosen scenario.
        """
        effective_scenario = scenario or self.default_scenario

        # Check if pre-cancelled
        if payload.task_id in self._cancelled_runs:
            effective_scenario = "cancellation"

        target_file = (
            payload.allowed_file_context[0]
            if payload.allowed_file_context
            else "app/main.py"
        )

        if effective_scenario == "timeout":
            return AgentExecutionResult(
                agent_id=self.agent_id,
                model_name="mock-replay-v1 (simulated)",
                execution_status="TIMEOUT",
                git_patch="",
                modified_files=[],
                prompt_tokens=150,
                completion_tokens=10,
                duration_ms=min(payload.timeout_sec * 1000, 300000),
                raw_logs=(
                    "[SIMULATED EXECUTION] Agent execution timed out after exceeding timeout ceiling.\n"
                    f"[SIMULATED WATCHDOG] Terminated task {payload.task_id}."
                ),
                failure_reason=f"Execution timed out after {payload.timeout_sec}s.",
            )

        if effective_scenario == "cancellation":
            return AgentExecutionResult(
                agent_id=self.agent_id,
                model_name="mock-replay-v1 (simulated)",
                execution_status="CANCELLED",
                git_patch="",
                modified_files=[],
                prompt_tokens=80,
                completion_tokens=5,
                duration_ms=250,
                raw_logs="[SIMULATED EXECUTION] Task cancelled by user or orchestrator signal.",
                failure_reason="Execution was cancelled by orchestrator request.",
            )

        if effective_scenario == "failure":
            return AgentExecutionResult(
                agent_id=self.agent_id,
                model_name="mock-replay-v1 (simulated)",
                execution_status="FAILED",
                git_patch="",
                modified_files=[],
                prompt_tokens=200,
                completion_tokens=30,
                duration_ms=1200,
                raw_logs=(
                    "[SIMULATED EXECUTION] Agent encountered internal exception:\n"
                    "SyntaxError: unexpected EOF while parsing simulated model output."
                ),
                failure_reason="Simulated internal agent exception during code synthesis.",
            )

        if effective_scenario == "empty_patch":
            return AgentExecutionResult(
                agent_id=self.agent_id,
                model_name="mock-replay-v1 (simulated)",
                execution_status="COMPLETED",
                git_patch="",
                modified_files=[],
                prompt_tokens=300,
                completion_tokens=50,
                duration_ms=850,
                raw_logs="[SIMULATED EXECUTION] Agent completed analysis but made no file changes.",
                failure_reason=None,
            )

        if effective_scenario == "malformed_patch":
            return AgentExecutionResult(
                agent_id=self.agent_id,
                model_name="mock-replay-v1 (simulated)",
                execution_status="COMPLETED",
                git_patch="MALFORMED DIFF HEADER\n@@ corrupt chunk header @@\n+broken line",
                modified_files=[target_file],
                prompt_tokens=320,
                completion_tokens=60,
                duration_ms=920,
                raw_logs="[SIMULATED EXECUTION] Emitted malformed unified diff patch.",
                failure_reason=None,
            )

        # Default: success scenario
        clean_patch = (
            f"diff --git a/{target_file} b/{target_file}\n"
            f"--- a/{target_file}\n"
            f"+++ b/{target_file}\n"
            "@@ -1,3 +1,6 @@\n"
            "+# Simulated implementation for task\n"
            "+def simulated_feature():\n"
            "+    return 'simulated_success'\n"
        )

        return AgentExecutionResult(
            agent_id=self.agent_id,
            model_name="mock-replay-v1 (simulated)",
            execution_status="COMPLETED",
            git_patch=clean_patch,
            modified_files=[target_file],
            prompt_tokens=420,
            completion_tokens=180,
            duration_ms=1450,
            raw_logs=(
                f"[SIMULATED EXECUTION] Loaded task: {payload.task_title}\n"
                f"[SIMULATED EXECUTION] Context files analyzed: {payload.allowed_file_context}\n"
                f"[SIMULATED EXECUTION] Synthesized patch for: {target_file}\n"
                "[SIMULATED EXECUTION] Patch generated cleanly without host code execution."
            ),
            failure_reason=None,
        )

    async def cancel_run(self, run_id: str) -> bool:
        """Records the run as cancelled to prevent orphan execution tasks."""
        self._cancelled_runs.add(run_id)
        return True

    async def stream_logs(self, run_id: str) -> AsyncIterator[str]:
        """Asynchronously streams deterministic simulated log events."""
        log_steps = [
            f"[SIMULATED LOG: {run_id}] Step 1: Ingesting task prompt and codebase hierarchy...",
            f"[SIMULATED LOG: {run_id}] Step 2: Formulating solution architecture...",
            f"[SIMULATED LOG: {run_id}] Step 3: Generating unified diff modifications...",
            f"[SIMULATED LOG: {run_id}] Step 4: Finalizing execution response (Simulation Complete).",
        ]
        for step in log_steps:
            if run_id in self._cancelled_runs:
                yield f"[SIMULATED LOG: {run_id}] Execution halted due to cancellation signal."
                break
            yield step
            await asyncio.sleep(0.01)
