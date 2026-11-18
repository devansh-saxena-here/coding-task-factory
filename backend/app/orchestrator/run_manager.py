"""
Benchmark Run Manager — Day 11 Step 4.

Coordinates the end-to-end benchmark evaluation lifecycle:
- Registers and retrieves agent adapters.
- Creates and tracks BenchmarkRun records.
- Dispatches candidate agents sequentially (concurrency = 1).
- Enforces strict trust boundaries: consuming verifier-produced TestExecutionRecords.
- Invokes ScoringEngine to calculate multi-dimensional scorecards.
- Selects winning agents objectively and generates BenchmarkReport outputs.
- Handles cancellation, timeouts, and adapter exceptions cleanly.

Zero untrusted code is executed on the host.
"""

import asyncio
from datetime import datetime, timezone
import uuid

from app.orchestrator.adapters.base import AgentAdapter
from app.orchestrator.adapters.mock import MockReplayAdapter
from app.orchestrator.scoring_engine import ScoringEngine
from app.schemas.orchestrator import (
    AgentExecutionResult,
    AgentPromptPayload,
    AgentRun,
    BenchmarkReport,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkRunStatus,
    EvaluationResult,
    TestExecutionRecord,
)
from app.schemas.task import TaskResponse


class RunManager:
    """
    Lightweight, in-memory orchestrator managing benchmark evaluation runs.
    
    Coordinates agent adapters sequentially and ensures that evaluation scores
    and Harbor rewards originate strictly from verifier evidence rather than
    unverified agent claims.
    """

    def __init__(self, pre_register_defaults: bool = True):
        self._adapters: dict[str, AgentAdapter] = {}
        self._runs: dict[str, BenchmarkRunResponse] = {}
        self._reports: dict[str, BenchmarkReport] = {}
        self._cancellation_requested: set[str] = set()

        if pre_register_defaults:
            self.register_adapter(MockReplayAdapter())

    # ── Adapter Registry ─────────────────────────────────────────────

    def register_adapter(self, adapter: AgentAdapter, overwrite: bool = False) -> None:
        """Registers an AI coding agent adapter."""
        if not overwrite and adapter.agent_id in self._adapters:
            raise ValueError(f"Agent adapter with id '{adapter.agent_id}' is already registered.")
        self._adapters[adapter.agent_id] = adapter

    def get_adapter(self, agent_id: str) -> AgentAdapter:
        """Retrieves a registered agent adapter by ID."""
        if agent_id not in self._adapters:
            raise KeyError(f"Agent adapter '{agent_id}' not found.")
        return self._adapters[agent_id]

    def list_adapters(self) -> list[AgentAdapter]:
        """Lists all registered agent adapters."""
        return list(self._adapters.values())

    # ── Benchmark Run Creation ───────────────────────────────────────

    def create_benchmark_run(
        self,
        request: BenchmarkRunRequest,
        task: TaskResponse,
    ) -> BenchmarkRunResponse:
        """
        Validates task ID and agent configuration IDs, initializing an in-memory run.
        
        Raises:
            ValueError: If task IDs mismatch or any requested agent ID is unknown.
        """
        if request.task_id != task.id:
            raise ValueError(
                f"Task ID mismatch: request.task_id '{request.task_id}' != task.id '{task.id}'"
            )

        # Validate that all requested agents exist
        for agent_id in request.agent_config_ids:
            if agent_id not in self._adapters:
                raise ValueError(
                    f"Unknown agent ID '{agent_id}'. Registered agents: {list(self._adapters.keys())}"
                )

        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        run_response = BenchmarkRunResponse(
            run_id=run_id,
            task_id=task.id,
            status="PENDING",
            agent_config_ids=request.agent_config_ids,
            created_at=now,
        )

        initial_agent_runs = [
            AgentRun(
                agent_run_id=str(uuid.uuid4()),
                benchmark_run_id=run_id,
                agent_id=aid,
                status="NOT_RUN",
            )
            for aid in request.agent_config_ids
        ]

        initial_report = BenchmarkReport(
            run_id=run_id,
            task_id=task.id,
            status="PENDING",
            created_at=now,
            agent_runs=initial_agent_runs,
            evaluation_results=[],
            winner_agent_id=None,
            summary=f"Benchmark run queued for {len(request.agent_config_ids)} agents.",
        )

        self._runs[run_id] = run_response
        self._reports[run_id] = initial_report

        return run_response

    # ── Benchmark Execution & Coordination ───────────────────────────

    async def execute_benchmark_run(
        self,
        run_id: str,
        task: TaskResponse,
        test_records_by_agent: dict[str, TestExecutionRecord] | None = None,
    ) -> BenchmarkReport:
        """
        Executes a benchmark run sequentially across all queued agents (concurrency = 1).
        
        Args:
            run_id: UUID of the registered benchmark run.
            task: Task specification under evaluation.
            test_records_by_agent: Verifier-produced test records mapped by agent_id.
                                   If None or omitted, verifier evidence is missing.
                                   
        Returns:
            Finalized BenchmarkReport containing scorecards and ranking.
        """
        if run_id not in self._runs:
            raise KeyError(f"Benchmark run '{run_id}' not found.")
        if task.id != self._runs[run_id].task_id:
            raise ValueError(f"Task ID mismatch for run '{run_id}'.")

        run_resp = self._runs[run_id]
        report = self._reports[run_id]
        test_records = test_records_by_agent or {}

        # Check for pre-cancellation
        if run_id in self._cancellation_requested:
            for ar in report.agent_runs:
                ar.status = "CANCELLED"
            report.status = "CANCELLED"
            report.completed_at = datetime.now(timezone.utc).isoformat()
            report.summary = "Benchmark run was cancelled before execution began."
            run_resp.status = "CANCELLED"
            return report

        run_resp.status = "RUNNING"
        report.status = "RUNNING"
        evaluation_results: list[EvaluationResult] = []

        # ── Sequential Dispatch (Concurrency = 1) ────────────────────
        for agent_run in report.agent_runs:
            # Check for cancellation between sequential agents
            if run_id in self._cancellation_requested:
                agent_run.status = "CANCELLED"
                continue

            agent_id = agent_run.agent_id
            adapter = self._adapters.get(agent_id)

            if not adapter:
                agent_run.status = "FAILED"
                agent_run.execution_result = AgentExecutionResult(
                    agent_id=agent_id,
                    model_name="unknown",
                    execution_status="FAILED",
                    failure_reason=f"Adapter '{agent_id}' is no longer registered.",
                )
                continue

            agent_run.status = "RUNNING"
            agent_run.started_at = datetime.now(timezone.utc).isoformat()

            payload = AgentPromptPayload(
                task_id=task.id,
                task_title=task.title,
                instruction_markdown=(
                    f"### {task.title}\n\n{task.description}\n\n"
                    "### Requirements:\n"
                    + "\n".join(f"- {r}" for r in task.requirements)
                    + "\n\n### Acceptance Criteria:\n"
                    + "\n".join(f"- {ac}" for ac in task.acceptance_criteria)
                ),
                starting_commit_sha=task.starting_commit_sha,
                allowed_file_context=task.relevant_files,
                timeout_sec=getattr(adapter, "timeout_sec", 300),
            )

            # Dispatch task safely with error boundaries
            try:
                execution_result = await adapter.dispatch_task(payload, "")
            except asyncio.CancelledError:
                execution_result = AgentExecutionResult(
                    agent_id=agent_id,
                    model_name=getattr(adapter, "model_name", "unknown"),
                    execution_status="CANCELLED",
                    failure_reason="Execution cancelled by orchestrator.",
                )
            except Exception as exc:
                execution_result = AgentExecutionResult(
                    agent_id=agent_id,
                    model_name=getattr(adapter, "model_name", "unknown"),
                    execution_status="FAILED",
                    failure_reason=f"Adapter execution exception: {exc}",
                )

            agent_run.completed_at = datetime.now(timezone.utc).isoformat()
            agent_run.status = execution_result.execution_status
            agent_run.execution_result = execution_result

            # ── Verifier Scoring Integration ─────────────────────────
            # Trust Boundary: We strictly use the independently produced verifier record.
            # An agent's self-reported success or mock generation never fabricates passing tests.
            test_record = test_records.get(agent_id)
            is_mock = isinstance(adapter, MockReplayAdapter)

            eval_res = ScoringEngine.evaluate(
                agent_run_id=agent_run.agent_run_id,
                benchmark_run_id=run_id,
                agent_id=agent_id,
                execution_result=execution_result,
                test_record=test_record,
                allowed_files=task.relevant_files,
                is_simulated=is_mock,
            )
            evaluation_results.append(eval_res)

        # ── Finalize Run Status & Select Winner ──────────────────────
        now_completed = datetime.now(timezone.utc).isoformat()
        report.completed_at = now_completed
        report.evaluation_results = evaluation_results

        if run_id in self._cancellation_requested:
            overall_status: BenchmarkRunStatus = "CANCELLED"
        elif all(ar.status == "FAILED" for ar in report.agent_runs):
            overall_status = "FAILED"
        else:
            overall_status = "COMPLETED"

        report.status = overall_status
        run_resp.status = overall_status

        # ── Winner Selection Rules ───────────────────────────────────
        # A winner is identified ONLY if verifiable evidence demonstrates non-zero success.
        # If all scores are 0.0 or no agent passed, winner is None.
        eligible_evals = [
            er for er in evaluation_results
            if er.composite_score > 0.0
        ]

        if eligible_evals:
            # Sort by composite score (descending), then harbor reward (descending)
            eligible_evals.sort(
                key=lambda er: (
                    er.composite_score,
                    er.harbor_reward,
                    -er.test_record.duration_ms if er.test_record else 0,
                ),
                reverse=True,
            )
            report.winner_agent_id = eligible_evals[0].agent_id
        else:
            report.winner_agent_id = None

        report.summary = self._build_report_summary(report)
        self._reports[run_id] = report

        return report

    # ── Cancellation & Retrieval ─────────────────────────────────────

    async def cancel_run(self, run_id: str) -> bool:
        """
        Issues cancellation for a benchmark run and aborts its active adapter.
        """
        if run_id not in self._runs:
            return False

        self._cancellation_requested.add(run_id)

        # Notify all adapters
        for adapter in self._adapters.values():
            try:
                await adapter.cancel_run(run_id)
            except Exception:
                pass

        if run_id in self._reports and self._reports[run_id].status == "PENDING":
            self._reports[run_id].status = "CANCELLED"
            self._runs[run_id].status = "CANCELLED"

        return True

    def get_run(self, run_id: str) -> BenchmarkRunResponse:
        """Retrieves the live status of a benchmark run."""
        if run_id not in self._runs:
            raise KeyError(f"Benchmark run '{run_id}' not found.")
        return self._runs[run_id]

    def get_report(self, run_id: str) -> BenchmarkReport:
        """Retrieves the full report of a benchmark run."""
        if run_id not in self._reports:
            raise KeyError(f"Benchmark report for run '{run_id}' not found.")
        return self._reports[run_id]

    # ── Summary Helper ───────────────────────────────────────────────

    def _build_report_summary(self, report: BenchmarkReport) -> str:
        total = len(report.agent_runs)
        completed = sum(1 for ar in report.agent_runs if ar.status == "COMPLETED")
        failed = sum(1 for ar in report.agent_runs if ar.status == "FAILED")
        timeouts = sum(1 for ar in report.agent_runs if ar.status == "TIMEOUT")
        cancelled = sum(1 for ar in report.agent_runs if ar.status == "CANCELLED")

        lines = [
            f"Benchmark Run {report.run_id} ({report.status}).",
            f"Evaluated {total} agents: {completed} completed, {failed} failed, {timeouts} timeouts, {cancelled} cancelled.",
        ]

        if report.winner_agent_id:
            winner_eval = next((er for er in report.evaluation_results if er.agent_id == report.winner_agent_id), None)
            score_str = f"{winner_eval.composite_score:.4f}" if winner_eval else "N/A"
            lines.append(f"Top Performer: {report.winner_agent_id} (Composite Score: {score_str}).")
        else:
            lines.append("No winning agent established (insufficient test evidence or zero passing scores).")

        return " ".join(lines)
