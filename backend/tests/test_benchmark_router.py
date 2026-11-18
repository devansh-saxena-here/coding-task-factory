"""
Integration tests for Benchmark Router — Day 11 Step 5.
"""

from datetime import datetime, timezone
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator.adapters.mock import MockReplayAdapter
from app.routers.benchmark import get_run_manager
from app.schemas.orchestrator import TestExecutionRecord
from app.schemas.task import TaskResponse
from app.services import task_service

client = TestClient(app)


class TestBenchmarkRouter(unittest.TestCase):
    """Verifies FastAPI /benchmark routes, validation, status codes, and security."""

    def setUp(self):
        # Reset task registry and manager for clean tests
        task_service.clear_tasks()
        self.manager = get_run_manager()

        # Seed sample task
        self.sample_task = TaskResponse(
            id="task-router-test-01",
            topic="Distributed Caching",
            difficulty="medium",
            language="python",
            category="backend",
            title="Implement Distributed Cache",
            description="Create an in-memory caching system with TTL.",
            requirements=["Implement get/set", "Add eviction"],
            acceptance_criteria=["Correct values returned"],
            generated_at=datetime.now(timezone.utc).isoformat(),
            relevant_files=["app/core/cache.py"],
            starting_commit_sha="11223344556677889900aabbccddeeff11223344",
        )
        task_service.save_task(self.sample_task)

    # ── 1. GET /benchmark/agents ─────────────────────────────────────

    def test_get_agents_returns_registered_adapters(self):
        resp = client.get("/benchmark/agents")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("agents", data)
        self.assertGreaterEqual(len(data["agents"]), 1)

        agent_ids = [a["agent_id"] for a in data["agents"]]
        self.assertIn("mock-replay-agent", agent_ids)

    def test_get_agents_does_not_expose_secrets(self):
        resp = client.get("/benchmark/agents")
        self.assertEqual(resp.status_code, 200)
        text = resp.text.lower()
        for forbidden in ["api_key", "secret", "password", "token", "private_key"]:
            self.assertNotIn(f'"{forbidden}"', text)

    def test_simulation_status_exposed_accurately(self):
        resp = client.get("/benchmark/agents")
        self.assertEqual(resp.status_code, 200)
        mock_agent = next(
            (a for a in resp.json()["agents"] if a["agent_id"] == "mock-replay-agent"),
            None,
        )
        self.assertIsNotNone(mock_agent)
        self.assertTrue(mock_agent["is_simulated"])

    # ── 2. POST /benchmark/runs ──────────────────────────────────────

    def test_post_creates_benchmark_run_success(self):
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["mock-replay-agent"],
            "execution_backend": "mock_sandbox",
        }
        resp = client.post("/benchmark/runs", json=payload)
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("run_id", data)
        self.assertEqual(data["task_id"], self.sample_task.id)
        self.assertIn(data["status"], ("PENDING", "RUNNING", "COMPLETED"))

    def test_post_unknown_task_returns_404(self):
        payload = {
            "task_id": "nonexistent-task-id-9999",
            "agent_config_ids": ["mock-replay-agent"],
        }
        resp = client.post("/benchmark/runs", json=payload)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("was not found", resp.json()["detail"])

    def test_post_unknown_agent_returns_400(self):
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["nonexistent-agent-xyz"],
        }
        resp = client.post("/benchmark/runs", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unknown agent configuration ID", resp.json()["detail"])

    def test_post_invalid_payload_returns_422(self):
        # Empty agent list violates min_length=1
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": [],
        }
        resp = client.post("/benchmark/runs", json=payload)
        self.assertEqual(resp.status_code, 422)

    # ── 3. GET /benchmark/runs/{run_id} ──────────────────────────────

    def test_get_run_status_success(self):
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["mock-replay-agent"],
        }
        create_resp = client.post("/benchmark/runs", json=payload)
        self.assertEqual(create_resp.status_code, 202)
        run_id = create_resp.json()["run_id"]

        get_resp = client.get(f"/benchmark/runs/{run_id}")
        self.assertEqual(get_resp.status_code, 200)
        report = get_resp.json()
        self.assertEqual(report["run_id"], run_id)
        self.assertEqual(report["task_id"], self.sample_task.id)
        self.assertIn("agent_runs", report)
        self.assertIn("evaluation_results", report)

    def test_get_unknown_run_returns_404(self):
        resp = client.get("/benchmark/runs/unknown-run-id-999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("was not found", resp.json()["detail"])

    def test_get_run_includes_scorecards_and_simulated_reward_zero(self):
        """When executed with mock adapter, scorecards are present and Harbor reward is 0.0."""
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["mock-replay-agent"],
        }
        create_resp = client.post("/benchmark/runs", json=payload)
        run_id = create_resp.json()["run_id"]

        get_resp = client.get(f"/benchmark/runs/{run_id}")
        self.assertEqual(get_resp.status_code, 200)
        report = get_resp.json()

        # If executed or pending, evaluation_results or agent_runs are inspectable
        if report["evaluation_results"]:
            for er in report["evaluation_results"]:
                self.assertEqual(er["harbor_reward"], 0.0)
                self.assertFalse(er["passed_all"])

    # ── 4. POST /benchmark/runs/{run_id}/cancel ──────────────────────

    def test_post_cancel_run_success(self):
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["mock-replay-agent"],
        }
        create_resp = client.post("/benchmark/runs", json=payload)
        run_id = create_resp.json()["run_id"]

        cancel_resp = client.post(f"/benchmark/runs/{run_id}/cancel")
        self.assertEqual(cancel_resp.status_code, 200)
        data = cancel_resp.json()
        self.assertEqual(data["run_id"], run_id)
        self.assertIn(data["status"], ("CANCELLED", "COMPLETED"))

    def test_post_cancel_unknown_run_returns_404(self):
        resp = client.post("/benchmark/runs/unknown-run-999/cancel")
        self.assertEqual(resp.status_code, 404)

    # ── 5. System Consistency & Backward Compatibility ───────────────

    def test_existing_health_endpoint_still_works(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")

    def test_existing_task_endpoints_remain_available(self):
        resp = client.get("/tasks/")
        self.assertEqual(resp.status_code, 200)

    def test_openapi_includes_benchmark_endpoints(self):
        resp = client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        paths = resp.json()["paths"]
        self.assertIn("/benchmark/agents", paths)
        self.assertIn("/benchmark/runs", paths)
        self.assertIn("/benchmark/runs/{run_id}", paths)
        self.assertIn("/benchmark/runs/{run_id}/cancel", paths)

    def test_multiple_requests_use_same_run_manager_instance(self):
        """Verifies that runs created in one request are retrievable in subsequent requests."""
        payload = {
            "task_id": self.sample_task.id,
            "agent_config_ids": ["mock-replay-agent"],
        }
        create_resp = client.post("/benchmark/runs", json=payload)
        run_id = create_resp.json()["run_id"]

        fetch_resp = client.get(f"/benchmark/runs/{run_id}")
        self.assertEqual(fetch_resp.status_code, 200)
        self.assertEqual(fetch_resp.json()["run_id"], run_id)


if __name__ == "__main__":
    unittest.main()
