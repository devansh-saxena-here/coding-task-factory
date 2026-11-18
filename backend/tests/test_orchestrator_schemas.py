"""
Tests for Orchestrator Schemas & Agent Adapter Protocol — Day 11 Step 2.
"""

import asyncio
from datetime import datetime, timezone
import json
import unittest
from typing import AsyncIterator

from pydantic import ValidationError

from app.orchestrator.adapters.base import AgentAdapter
from app.schemas.orchestrator import (
    AgentConfiguration,
    AgentExecutionResult,
    AgentPromptPayload,
    AgentRun,
    BenchmarkReport,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    EvaluationResult,
    TestExecutionRecord,
)


# ── Concrete Dummy Adapter for Interface Testing ─────────────────────

class DummyTestAdapter(AgentAdapter):
    def __init__(self, agent_id: str = "dummy-agent", display_name: str = "Dummy Test Agent"):
        self._agent_id = agent_id
        self._display_name = display_name

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
    ) -> AgentExecutionResult:
        return AgentExecutionResult(
            agent_id=self.agent_id,
            model_name="dummy-v1",
            execution_status="COMPLETED",
            git_patch="diff --git a/test.py b/test.py\n+print('hello')",
            modified_files=["test.py"],
            prompt_tokens=150,
            completion_tokens=45,
            duration_ms=1200,
            raw_logs="Execution finished cleanly.",
        )

    async def cancel_run(self, run_id: str) -> bool:
        return True

    async def stream_logs(self, run_id: str) -> AsyncIterator[str]:
        yield "Step 1: Inspecting code"
        yield "Step 2: Completed"


class TestOrchestratorSchemas(unittest.TestCase):
    """Unit tests for orchestrator Pydantic v2 schemas and validation logic."""

    # ── 1. AgentConfiguration Tests ──────────────────────────────────

    def test_agent_configuration_valid(self):
        config = AgentConfiguration(
            agent_id="gemini-flash",
            display_name="Gemini 3.8 Flash",
            provider="google",
            model_name="gemini-2.5-flash",
            adapter_type="api",
            enabled=True,
            timeout_sec=300,
            parameters={"temperature": 0.2, "max_tokens": 4096},
        )
        self.assertEqual(config.agent_id, "gemini-flash")
        self.assertEqual(config.provider, "google")
        self.assertEqual(config.parameters["temperature"], 0.2)

    def test_agent_configuration_invalid_agent_id(self):
        with self.assertRaises(ValidationError) as ctx:
            AgentConfiguration(
                agent_id="invalid agent id with spaces!",
                display_name="Invalid Agent",
                provider="google",
                model_name="gemini-flash",
            )
        self.assertIn("agent_id", str(ctx.exception))

    def test_agent_configuration_rejects_secret_leakage(self):
        """Rejects sensitive keys such as api_key, secret, or password in parameters."""
        for forbidden_key in ["api_key", "secret", "secret_key", "token", "password", "private_key"]:
            with self.subTest(forbidden_key=forbidden_key):
                with self.assertRaises(ValidationError) as ctx:
                    AgentConfiguration(
                        agent_id="test-agent",
                        display_name="Test Agent",
                        provider="openai",
                        model_name="gpt-4o",
                        parameters={forbidden_key: "super_secret_value_123"},
                    )
                self.assertIn("Security violation: Sensitive key", str(ctx.exception))

    # ── 2. AgentPromptPayload Tests ──────────────────────────────────

    def test_agent_prompt_payload_valid(self):
        payload = AgentPromptPayload(
            task_id="task-1234",
            task_title="Implement Redis Caching",
            instruction_markdown="### Task\nBuild Redis cache backend.",
            starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
            allowed_file_context=["app/core/cache.py", "app/main.py"],
            timeout_sec=600,
        )
        self.assertEqual(payload.task_id, "task-1234")
        self.assertEqual(len(payload.allowed_file_context), 2)
        self.assertEqual(payload.timeout_sec, 600)

    def test_agent_prompt_payload_missing_required(self):
        with self.assertRaises(ValidationError):
            AgentPromptPayload(
                task_id="task-123",
                # missing task_title and instruction_markdown
            )

    def test_agent_prompt_payload_invalid_timeout(self):
        with self.assertRaises(ValidationError):
            AgentPromptPayload(
                task_id="task-123",
                task_title="Title",
                instruction_markdown="Instructions",
                timeout_sec=5,  # less than minimum 10
            )

    # ── 3. AgentExecutionResult Tests ────────────────────────────────

    def test_agent_execution_result_completed_valid(self):
        res = AgentExecutionResult(
            agent_id="agent-1",
            model_name="claude-3-7",
            execution_status="COMPLETED",
            git_patch="diff --git a/a.py b/a.py",
            modified_files=["a.py"],
            prompt_tokens=500,
            completion_tokens=200,
            duration_ms=4500,
            raw_logs="Clean run",
            failure_reason=None,
        )
        self.assertEqual(res.execution_status, "COMPLETED")
        self.assertIsNone(res.failure_reason)

    def test_agent_execution_result_completed_cannot_have_failure_reason(self):
        with self.assertRaises(ValidationError) as ctx:
            AgentExecutionResult(
                agent_id="agent-1",
                model_name="claude-3-7",
                execution_status="COMPLETED",
                failure_reason="Something failed unexpectedly",
            )
        self.assertIn("failure_reason must be None", str(ctx.exception))

    def test_agent_execution_result_failed_assigns_default_reason(self):
        res = AgentExecutionResult(
            agent_id="agent-1",
            model_name="claude-3-7",
            execution_status="FAILED",
        )
        self.assertEqual(res.execution_status, "FAILED")
        self.assertIn("FAILED", res.failure_reason)

    def test_agent_execution_result_not_run_semantics(self):
        res = AgentExecutionResult(
            agent_id="agent-1",
            model_name="claude-3-7",
            execution_status="NOT_RUN",
            duration_ms=0,
            git_patch="",
        )
        self.assertEqual(res.execution_status, "NOT_RUN")
        self.assertEqual(res.duration_ms, 0)

        # NOT_RUN cannot have positive duration or non-empty patch
        with self.assertRaises(ValidationError):
            AgentExecutionResult(
                agent_id="agent-1",
                model_name="claude-3-7",
                execution_status="NOT_RUN",
                duration_ms=1000,
            )

        with self.assertRaises(ValidationError):
            AgentExecutionResult(
                agent_id="agent-1",
                model_name="claude-3-7",
                execution_status="NOT_RUN",
                git_patch="diff ...",
            )

    def test_agent_execution_result_negative_tokens_rejected(self):
        with self.assertRaises(ValidationError):
            AgentExecutionResult(
                agent_id="agent-1",
                model_name="test-model",
                execution_status="COMPLETED",
                prompt_tokens=-10,
            )

    # ── 4. BenchmarkRunRequest & Response ────────────────────────────

    def test_benchmark_run_request_and_response(self):
        req = BenchmarkRunRequest(
            task_id="task-9999",
            agent_config_ids=["gemini-flash", "claude-code"],
            execution_backend="mock_sandbox",
        )
        self.assertEqual(len(req.agent_config_ids), 2)

        resp = BenchmarkRunResponse(
            task_id=req.task_id,
            agent_config_ids=req.agent_config_ids,
        )
        self.assertIsNotNone(resp.run_id)
        self.assertEqual(resp.status, "PENDING")
        self.assertIn("T", resp.created_at)

    def test_benchmark_run_request_empty_agents_rejected(self):
        with self.assertRaises(ValidationError):
            BenchmarkRunRequest(
                task_id="task-1",
                agent_config_ids=[],  # min_length is 1
            )

    # ── 5. AgentRun Record Tests ─────────────────────────────────────

    def test_agent_run_lifecycle_record(self):
        ar = AgentRun(
            benchmark_run_id="run-101",
            agent_id="agent-alpha",
            status="NOT_RUN",
        )
        self.assertEqual(ar.status, "NOT_RUN")
        self.assertIsNone(ar.started_at)
        self.assertIsNone(ar.completed_at)

    # ── 6. TestExecutionRecord Tests ─────────────────────────────────

    def test_test_execution_record_valid(self):
        rec = TestExecutionRecord(
            test_suite_id="ts-001",
            feature_tests_total=5,
            feature_tests_passed=4,
            feature_tests_failed=1,
            regression_tests_total=10,
            regression_tests_passed=10,
            regression_tests_failed=0,
            duration_ms=2500,
        )
        self.assertEqual(rec.feature_tests_passed, 4)
        self.assertEqual(rec.regression_tests_passed, 10)

    def test_test_execution_record_exceeding_total_fails(self):
        with self.assertRaises(ValidationError) as ctx:
            TestExecutionRecord(
                test_suite_id="ts-001",
                feature_tests_total=5,
                feature_tests_passed=4,
                feature_tests_failed=2,  # 4 + 2 = 6 > 5
            )
        self.assertIn("exceeds total", str(ctx.exception))

    # ── 7. EvaluationResult Tests ────────────────────────────────────

    def test_evaluation_result_valid_pass(self):
        eval_res = EvaluationResult(
            agent_run_id="ar-001",
            benchmark_run_id="run-001",
            agent_id="gemini-flash",
            feature_pass_rate=1.0,
            regression_preservation_rate=1.0,
            diff_quality_score=1.0,
            composite_score=1.0,
            harbor_reward=1.0,
            passed_all=True,
            failure_diagnostics=[],
        )
        self.assertEqual(eval_res.harbor_reward, 1.0)
        self.assertTrue(eval_res.passed_all)

    def test_evaluation_result_score_boundary_enforcement(self):
        """Scores must be within [0.0, 1.0]."""
        with self.assertRaises(ValidationError):
            EvaluationResult(
                agent_run_id="ar-1",
                benchmark_run_id="run-1",
                agent_id="test",
                feature_pass_rate=1.2,  # > 1.0
                regression_preservation_rate=1.0,
                composite_score=1.0,
                harbor_reward=1.0,
                passed_all=True,
            )

        with self.assertRaises(ValidationError):
            EvaluationResult(
                agent_run_id="ar-1",
                benchmark_run_id="run-1",
                agent_id="test",
                feature_pass_rate=-0.1,  # < 0.0
                regression_preservation_rate=1.0,
                composite_score=0.5,
                harbor_reward=0.0,
                passed_all=False,
            )

    def test_evaluation_result_harbor_reward_must_be_binary(self):
        """Harbor reward must be strictly 0.0 or 1.0."""
        with self.assertRaises(ValidationError) as ctx:
            EvaluationResult(
                agent_run_id="ar-1",
                benchmark_run_id="run-1",
                agent_id="test",
                feature_pass_rate=0.75,
                regression_preservation_rate=1.0,
                composite_score=0.85,
                harbor_reward=0.75,  # Non-binary reward invalid in Harbor
                passed_all=False,
            )
        self.assertIn("harbor_reward must be exactly 0.0 or 1.0", str(ctx.exception))

    def test_evaluation_result_passed_all_consistency(self):
        with self.assertRaises(ValidationError) as ctx:
            EvaluationResult(
                agent_run_id="ar-1",
                benchmark_run_id="run-1",
                agent_id="test",
                feature_pass_rate=1.0,
                regression_preservation_rate=1.0,
                composite_score=1.0,
                harbor_reward=0.0,  # Inconsistent with passed_all=True
                passed_all=True,
            )
        self.assertIn("harbor_reward must be 1.0", str(ctx.exception))

    # ── 8. BenchmarkReport Tests ─────────────────────────────────────

    def test_benchmark_report_valid(self):
        now = datetime.now(timezone.utc).isoformat()
        run_id = "run-valid-99"

        ar1 = AgentRun(
            benchmark_run_id=run_id,
            agent_id="agent-1",
            status="COMPLETED",
        )
        er1 = EvaluationResult(
            agent_run_id=ar1.agent_run_id,
            benchmark_run_id=run_id,
            agent_id="agent-1",
            feature_pass_rate=1.0,
            regression_preservation_rate=1.0,
            composite_score=1.0,
            harbor_reward=1.0,
            passed_all=True,
        )

        report = BenchmarkReport(
            run_id=run_id,
            task_id="task-100",
            status="COMPLETED",
            created_at=now,
            completed_at=now,
            agent_runs=[ar1],
            evaluation_results=[er1],
            winner_agent_id="agent-1",
            summary="Agent-1 passed all feature and regression checks.",
        )
        self.assertEqual(report.winner_agent_id, "agent-1")
        self.assertEqual(len(report.agent_runs), 1)

    def test_benchmark_report_mismatched_run_id_rejected(self):
        now = datetime.now(timezone.utc).isoformat()
        ar_mismatched = AgentRun(
            benchmark_run_id="different-run-id",
            agent_id="agent-1",
        )
        with self.assertRaises(ValidationError) as ctx:
            BenchmarkReport(
                run_id="main-run-id",
                task_id="task-1",
                status="COMPLETED",
                created_at=now,
                agent_runs=[ar_mismatched],
            )
        self.assertIn("does not match report run_id", str(ctx.exception))

    def test_benchmark_report_invalid_winner_rejected(self):
        now = datetime.now(timezone.utc).isoformat()
        run_id = "run-1"
        ar1 = AgentRun(benchmark_run_id=run_id, agent_id="agent-1")

        with self.assertRaises(ValidationError) as ctx:
            BenchmarkReport(
                run_id=run_id,
                task_id="task-1",
                status="COMPLETED",
                created_at=now,
                agent_runs=[ar1],
                winner_agent_id="agent-nonexistent",  # Not in agent_runs
            )
        self.assertIn("not in the list of evaluated agents", str(ctx.exception))

    def test_json_serialization_roundtrip(self):
        """Verifies JSON serializability for API responses."""
        config = AgentConfiguration(
            agent_id="test-agent",
            display_name="Test Agent",
            provider="mock",
            model_name="mock-model",
            timeout_sec=120,
            parameters={"seed": 42},
        )
        dumped = config.model_dump_json()
        loaded = json.loads(dumped)
        self.assertEqual(loaded["agent_id"], "test-agent")
        self.assertEqual(loaded["parameters"]["seed"], 42)


# ── 9. AgentAdapter Protocol Tests ───────────────────────────────────

class TestAgentAdapterProtocol(unittest.IsolatedAsyncioTestCase):
    """Verifies that the AgentAdapter interface can be subclassed and executed asynchronously."""

    async def test_dummy_adapter_dispatch(self):
        adapter = DummyTestAdapter(agent_id="mock-agent", display_name="Mock Agent")
        self.assertEqual(adapter.agent_id, "mock-agent")
        self.assertEqual(adapter.display_name, "Mock Agent")

        payload = AgentPromptPayload(
            task_id="task-01",
            task_title="Sample Task",
            instruction_markdown="Sample instructions",
            timeout_sec=60,
        )

        res = await adapter.dispatch_task(payload, "/tmp/workspace")
        self.assertEqual(res.agent_id, "mock-agent")
        self.assertEqual(res.execution_status, "COMPLETED")
        self.assertEqual(res.modified_files, ["test.py"])
        self.assertIn("diff", res.git_patch)

    async def test_dummy_adapter_cancellation(self):
        adapter = DummyTestAdapter()
        cancelled = await adapter.cancel_run("run-123")
        self.assertTrue(cancelled)

    async def test_dummy_adapter_stream_logs(self):
        adapter = DummyTestAdapter()
        logs = []
        async for chunk in adapter.stream_logs("run-123"):
            logs.append(chunk)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0], "Step 1: Inspecting code")


if __name__ == "__main__":
    unittest.main()
