"""
Unit tests for MockReplayAdapter — Day 11 Step 3.
"""

import asyncio
import unittest

from app.orchestrator.adapters.mock import MockReplayAdapter
from app.schemas.orchestrator import AgentPromptPayload


class TestMockReplayAdapter(unittest.IsolatedAsyncioTestCase):
    """Verifies deterministic simulated execution of MockReplayAdapter."""

    def setUp(self):
        self.adapter = MockReplayAdapter(
            agent_id="test-mock-agent",
            display_name="Test Mock Agent (Simulated)",
        )
        self.payload = AgentPromptPayload(
            task_id="task-mock-01",
            task_title="Simulate Redis Cache Implementation",
            instruction_markdown="Build a Redis caching module in app/core/cache.py",
            starting_commit_sha="e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0",
            allowed_file_context=["app/core/cache.py"],
            timeout_sec=30,
        )

    async def test_mock_adapter_properties(self):
        self.assertEqual(self.adapter.agent_id, "test-mock-agent")
        self.assertEqual(self.adapter.display_name, "Test Mock Agent (Simulated)")

    async def test_mock_success_scenario(self):
        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace")
        self.assertEqual(res.agent_id, "test-mock-agent")
        self.assertEqual(res.execution_status, "COMPLETED")
        self.assertIn("diff --git", res.git_patch)
        self.assertEqual(res.modified_files, ["app/core/cache.py"])
        self.assertGreater(res.prompt_tokens, 0)
        self.assertGreater(res.completion_tokens, 0)
        self.assertGreater(res.duration_ms, 0)
        self.assertIsNone(res.failure_reason)
        self.assertIn("[SIMULATED EXECUTION]", res.raw_logs)

    async def test_mock_failure_scenario(self):
        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace", scenario="failure")
        self.assertEqual(res.execution_status, "FAILED")
        self.assertEqual(res.git_patch, "")
        self.assertIsNotNone(res.failure_reason)
        self.assertIn("exception", res.failure_reason.lower())

    async def test_mock_timeout_scenario(self):
        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace", scenario="timeout")
        self.assertEqual(res.execution_status, "TIMEOUT")
        self.assertEqual(res.git_patch, "")
        self.assertIsNotNone(res.failure_reason)
        self.assertIn("timed out", res.failure_reason.lower())
        self.assertEqual(res.duration_ms, 30000)

    async def test_mock_cancellation_scenario(self):
        # Cancel task first
        cancelled = await self.adapter.cancel_run(self.payload.task_id)
        self.assertTrue(cancelled)

        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace")
        self.assertEqual(res.execution_status, "CANCELLED")
        self.assertEqual(res.git_patch, "")
        self.assertIn("cancelled", res.failure_reason.lower())

    async def test_mock_empty_patch_scenario(self):
        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace", scenario="empty_patch")
        self.assertEqual(res.execution_status, "COMPLETED")
        self.assertEqual(res.git_patch, "")
        self.assertEqual(res.modified_files, [])
        self.assertIsNone(res.failure_reason)

    async def test_mock_malformed_patch_scenario(self):
        res = await self.adapter.dispatch_task(self.payload, "/fake/workspace", scenario="malformed_patch")
        self.assertEqual(res.execution_status, "COMPLETED")
        self.assertIn("MALFORMED", res.git_patch)
        self.assertEqual(res.modified_files, ["app/core/cache.py"])

    async def test_async_log_streaming(self):
        logs = []
        async for chunk in self.adapter.stream_logs("run-001"):
            logs.append(chunk)
        self.assertEqual(len(logs), 4)
        self.assertIn("[SIMULATED LOG: run-001]", logs[0])

    async def test_stream_logs_honors_cancellation(self):
        await self.adapter.cancel_run("run-cancelled")
        logs = []
        async for chunk in self.adapter.stream_logs("run-cancelled"):
            logs.append(chunk)
        self.assertEqual(len(logs), 1)
        self.assertIn("cancellation signal", logs[0])


if __name__ == "__main__":
    unittest.main()
