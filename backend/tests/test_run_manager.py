"""
Unit tests for Benchmark RunManager — Day 11 Step 4.
"""

import asyncio
from datetime import datetime, timezone
import unittest
from typing import AsyncIterator

from app.orchestrator.adapters.base import AgentAdapter
from app.orchestrator.adapters.mock import MockReplayAdapter
from app.orchestrator.run_manager import RunManager
from app.schemas.orchestrator import (
    AgentExecutionResult,
    AgentPromptPayload,
    BenchmarkRunRequest,
    TestExecutionRecord,
)
from app.schemas.task import TaskResponse


# ── Custom Test Adapters for Edge Cases ──────────────────────────────

class SlowMockAdapter(AgentAdapter):
    """Adapter that simulates a pause to test cancellation during dispatch."""
    def __init__(self, agent_id: str = "slow-agent"):
        self._agent_id = agent_id
        self._cancelled = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def display_name(self) -> str:
        return "Slow Agent"

    async def dispatch_task(
        self,
        payload: AgentPromptPayload,
        workspace_path: str,
    ) -> AgentExecutionResult:
        for _ in range(50):
            if self._cancelled:
                return AgentExecutionResult(
                    agent_id=self.agent_id,
                    model_name="slow-model",
                    execution_status="CANCELLED",
                    failure_reason="Slow execution cancelled",
                )
            await asyncio.sleep(0.01)

        return AgentExecutionResult(
            agent_id=self.agent_id,
            model_name="slow-model",
            execution_status="COMPLETED",
            git_patch="diff --git a/slow.py b/slow.py",
        )

    async def cancel_run(self, run_id: str) -> bool:
        self._cancelled = True
        return True

    async def stream_logs(self, run_id: str) -> AsyncIterator[str]:
        yield "Slow log"


class FailingAdapter(AgentAdapter):
    """Adapter that raises an unhandled exception to test error boundaries."""
    def __init__(self, agent_id: str = "failing-agent"):
        self._agent_id = agent_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def display_name(self) -> str:
        return "Failing Agent"

    async def dispatch_task(
        self,
        payload: AgentPromptPayload,
        workspace_path: str,
    ) -> AgentExecutionResult:
        raise RuntimeError("Fatal connection crash in adapter dispatch")

    async def cancel_run(self, run_id: str) -> bool:
        return True

    async def stream_logs(self, run_id: str) -> AsyncIterator[str]:
        yield "Crash"


class TestRunManager(unittest.IsolatedAsyncioTestCase):
    """Verifies RunManager coordination, lifecycle, trust boundaries, and scoring."""

    def setUp(self):
        self.manager = RunManager(pre_register_defaults=True)
        self.sample_task = TaskResponse(
            id="task-test-01",
            topic="Redis Caching",
            difficulty="medium",
            language="python",
            category="backend",
            title="Implement In-Memory Cache",
            description="Build a high performance in-memory caching module.",
            requirements=["Implement get and set", "Add TTL support"],
            acceptance_criteria=["Cache hits return stored value", "Cache misses return None"],
            generated_at=datetime.now(timezone.utc).isoformat(),
            relevant_files=["app/core/cache.py"],
            starting_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        )

    # ── 1. Agent Registration Tests ──────────────────────────────────

    def test_agent_registration_and_retrieval(self):
        adapter = MockReplayAdapter(agent_id="custom-mock", display_name="Custom Mock")
        self.manager.register_adapter(adapter)

        retrieved = self.manager.get_adapter("custom-mock")
        self.assertEqual(retrieved.agent_id, "custom-mock")
        self.assertIn("custom-mock", [a.agent_id for a in self.manager.list_adapters()])

    def test_duplicate_registration_fails(self):
        adapter = MockReplayAdapter(agent_id="mock-replay-agent")  # Already default
        with self.assertRaises(ValueError) as ctx:
            self.manager.register_adapter(adapter, overwrite=False)
        self.assertIn("already registered", str(ctx.exception))

    def test_unknown_agent_retrieval_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.manager.get_adapter("nonexistent-agent")

    # ── 2. Run Creation & Validation ─────────────────────────────────

    def test_create_benchmark_run_success(self):
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["mock-replay-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        self.assertIsNotNone(resp.run_id)
        self.assertEqual(resp.status, "PENDING")
        self.assertEqual(resp.task_id, self.sample_task.id)

        # Verify initial report exists and is PENDING
        report = self.manager.get_report(resp.run_id)
        self.assertEqual(report.status, "PENDING")
        self.assertEqual(len(report.agent_runs), 1)
        self.assertEqual(report.agent_runs[0].status, "NOT_RUN")

    def test_create_benchmark_run_task_id_mismatch_fails(self):
        req = BenchmarkRunRequest(
            task_id="wrong-task-id",
            agent_config_ids=["mock-replay-agent"],
        )
        with self.assertRaises(ValueError) as ctx:
            self.manager.create_benchmark_run(req, self.sample_task)
        self.assertIn("Task ID mismatch", str(ctx.exception))

    def test_create_benchmark_run_unknown_agent_fails(self):
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["unknown-agent-xyz"],
        )
        with self.assertRaises(ValueError) as ctx:
            self.manager.create_benchmark_run(req, self.sample_task)
        self.assertIn("Unknown agent ID", str(ctx.exception))

    # ── 3. Execution, Ordering & Scoring ─────────────────────────────

    async def test_successful_benchmark_run_with_verifier_evidence(self):
        """Single agent with valid verifier record completes and computes scorecard."""
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["mock-replay-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)

        # Verifier produces passing test record
        verifier_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=4,
            feature_tests_failed=0,
            regression_tests_total=6,
            regression_tests_passed=6,
            regression_tests_failed=0,
            duration_ms=400,
        )

        report = await self.manager.execute_benchmark_run(
            run_id=resp.run_id,
            task=self.sample_task,
            test_records_by_agent={"mock-replay-agent": verifier_record},
        )

        self.assertEqual(report.status, "COMPLETED")
        self.assertEqual(len(report.agent_runs), 1)
        self.assertEqual(report.agent_runs[0].status, "COMPLETED")
        self.assertEqual(len(report.evaluation_results), 1)

        eval_res = report.evaluation_results[0]
        self.assertEqual(eval_res.feature_pass_rate, 1.0)
        self.assertEqual(eval_res.regression_preservation_rate, 1.0)
        self.assertEqual(eval_res.composite_score, 1.0)
        # Trust boundary: Mock agent does NOT receive a real Harbor reward
        self.assertEqual(eval_res.harbor_reward, 0.0)
        self.assertFalse(eval_res.passed_all)
        self.assertTrue(any("[SIMULATED SCORE]" in d for d in eval_res.failure_diagnostics))

        # Top performer is established based on composite score
        self.assertEqual(report.winner_agent_id, "mock-replay-agent")
        self.assertIn("Top Performer", report.summary)

    async def test_sequential_dispatch_ordering(self):
        """Dispatches multiple agents strictly in the requested sequential order."""
        dispatch_order = []

        class OrderedAdapter(AgentAdapter):
            def __init__(self, name):
                self._name = name

            @property
            def agent_id(self):
                return self._name

            @property
            def display_name(self):
                return self._name

            async def dispatch_task(self, payload: AgentPromptPayload, workspace_path: str = "") -> AgentExecutionResult:
                dispatch_order.append(self._name)
                return AgentExecutionResult(
                    agent_id=self._name,
                    model_name="m",
                    execution_status="COMPLETED",
                    git_patch="",
                )

            async def cancel_run(self, run_id):
                return True

            async def stream_logs(self, run_id):
                yield "log"

        self.manager.register_adapter(OrderedAdapter("agent-first"))
        self.manager.register_adapter(OrderedAdapter("agent-second"))
        self.manager.register_adapter(OrderedAdapter("agent-third"))

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["agent-first", "agent-second", "agent-third"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        await self.manager.execute_benchmark_run(resp.run_id, self.sample_task)

        self.assertEqual(dispatch_order, ["agent-first", "agent-second", "agent-third"])

    async def test_missing_verifier_evidence_withholds_reward_and_score(self):
        """Completed agent with NO verifier evidence must not fabricate scores or rewards."""
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["mock-replay-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)

        # No test records provided (test_records_by_agent is empty)
        report = await self.manager.execute_benchmark_run(
            run_id=resp.run_id,
            task=self.sample_task,
            test_records_by_agent=None,
        )

        eval_res = report.evaluation_results[0]
        self.assertEqual(eval_res.composite_score, 0.0)
        self.assertEqual(eval_res.harbor_reward, 0.0)
        self.assertFalse(eval_res.passed_all)
        self.assertTrue(any("test record is missing" in d for d in eval_res.failure_diagnostics))
        self.assertIsNone(report.winner_agent_id)

    async def test_adapter_exception_handled_cleanly(self):
        """Adapter crashing does not crash RunManager; marks agent as FAILED."""
        self.manager.register_adapter(FailingAdapter("crasher"))

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["crasher"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        report = await self.manager.execute_benchmark_run(resp.run_id, self.sample_task)

        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.agent_runs[0].status, "FAILED")
        self.assertIn("Fatal connection crash", report.agent_runs[0].execution_result.failure_reason)
        self.assertIsNone(report.winner_agent_id)

    async def test_cancellation_before_execution(self):
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["mock-replay-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)

        # Cancel before starting
        await self.manager.cancel_run(resp.run_id)

        report = await self.manager.execute_benchmark_run(resp.run_id, self.sample_task)
        self.assertEqual(report.status, "CANCELLED")
        self.assertEqual(report.agent_runs[0].status, "CANCELLED")
        self.assertIn("cancelled before execution", report.summary)

    async def test_cancellation_during_execution(self):
        slow_adapter = SlowMockAdapter("slow-1")
        self.manager.register_adapter(slow_adapter)

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["slow-1"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)

        # Run execute in background task, cancel shortly after start
        exec_task = asyncio.create_task(
            self.manager.execute_benchmark_run(resp.run_id, self.sample_task)
        )
        await asyncio.sleep(0.02)
        await self.manager.cancel_run(resp.run_id)
        report = await exec_task

        self.assertEqual(report.status, "CANCELLED")
        self.assertEqual(report.agent_runs[0].status, "CANCELLED")

    async def test_cancellation_between_sequential_agents(self):
        """Cancelling during first agent cancels subsequent queued agents."""
        slow_adapter = SlowMockAdapter("slow-seq")
        self.manager.register_adapter(slow_adapter)
        self.manager.register_adapter(MockReplayAdapter(agent_id="queued-agent"))

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["slow-seq", "queued-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)

        exec_task = asyncio.create_task(
            self.manager.execute_benchmark_run(resp.run_id, self.sample_task)
        )
        await asyncio.sleep(0.02)
        await self.manager.cancel_run(resp.run_id)
        report = await exec_task

        self.assertEqual(report.status, "CANCELLED")
        # Both agents are cancelled
        self.assertEqual(report.agent_runs[0].status, "CANCELLED")
        self.assertEqual(report.agent_runs[1].status, "CANCELLED")

    async def test_winner_selection_highest_composite_score(self):
        """Selects agent with highest composite score as winner."""
        self.manager.register_adapter(MockReplayAdapter(agent_id="agent-high"))
        self.manager.register_adapter(MockReplayAdapter(agent_id="agent-low"))

        rec_high = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=4,
            regression_tests_total=4,
            regression_tests_passed=4,
        )
        rec_low = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=1,  # 25%
            regression_tests_total=4,
            regression_tests_passed=2,  # 50%
        )

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["agent-low", "agent-high"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        report = await self.manager.execute_benchmark_run(
            resp.run_id,
            self.sample_task,
            test_records_by_agent={"agent-high": rec_high, "agent-low": rec_low},
        )

        self.assertEqual(report.winner_agent_id, "agent-high")

    async def test_timeout_handling(self):
        """Adapter returning TIMEOUT is recorded as TIMEOUT and cannot win."""
        self.manager.register_adapter(
            MockReplayAdapter(agent_id="timeout-agent", default_scenario="timeout")
        )
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["timeout-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        report = await self.manager.execute_benchmark_run(resp.run_id, self.sample_task)

        self.assertEqual(report.status, "COMPLETED")
        self.assertEqual(report.agent_runs[0].status, "TIMEOUT")
        self.assertEqual(report.evaluation_results[0].composite_score, 0.0)
        self.assertIsNone(report.winner_agent_id)

    async def test_partial_run_handling_when_one_agent_fails_and_another_succeeds(self):
        """A failure in one agent does not corrupt subsequent successful agents."""
        self.manager.register_adapter(FailingAdapter("fail-1"))
        self.manager.register_adapter(MockReplayAdapter(agent_id="success-1"))

        valid_rec = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=2,
            feature_tests_passed=2,
            regression_tests_total=2,
            regression_tests_passed=2,
        )

        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["fail-1", "success-1"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        report = await self.manager.execute_benchmark_run(
            resp.run_id,
            self.sample_task,
            test_records_by_agent={"success-1": valid_rec},
        )

        self.assertEqual(report.status, "COMPLETED")
        self.assertEqual(report.agent_runs[0].status, "FAILED")
        self.assertEqual(report.agent_runs[1].status, "COMPLETED")
        self.assertEqual(report.winner_agent_id, "success-1")

    def test_get_run_and_report_success(self):
        req = BenchmarkRunRequest(
            task_id=self.sample_task.id,
            agent_config_ids=["mock-replay-agent"],
        )
        resp = self.manager.create_benchmark_run(req, self.sample_task)
        fetched_run = self.manager.get_run(resp.run_id)
        self.assertEqual(fetched_run.run_id, resp.run_id)

        fetched_report = self.manager.get_report(resp.run_id)
        self.assertEqual(fetched_report.run_id, resp.run_id)

    def test_get_run_and_report_not_found_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.manager.get_run("nonexistent-run")
        with self.assertRaises(KeyError):
            self.manager.get_report("nonexistent-run")

    async def test_cancel_nonexistent_run_returns_false(self):
        cancelled = await self.manager.cancel_run("nonexistent-run")
        self.assertFalse(cancelled)


if __name__ == "__main__":
    unittest.main()
