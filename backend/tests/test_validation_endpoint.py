"""
Integration tests for POST /tasks/validate endpoint — Day 8 Step 3.

Verifies end-to-end API validation behavior, schema compliance, ID and commit SHA
propagation, unsafe path rejection, missing sandbox handling, and backward compatibility.
Zero untrusted code is executed.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ── Reusable Test Data ──────────────────────────────────────────────

SAMPLE_TASK = {
    "id": "task-val-1234",
    "topic": "Codebase: store_api (Redis caching)",
    "difficulty": "medium",
    "language": "python",
    "category": "backend",
    "title": "Implement Redis Caching Layer for Store Endpoint",
    "description": "Add a Redis cache with 60s TTL to /items endpoint.",
    "requirements": ["Use redis-py connection pool"],
    "acceptance_criteria": ["GET /items returns cached responses on second call"],
    "generated_at": "2026-11-16T12:00:00+00:00",
    "project_name": "store_api",
    "relevant_files": ["app/cache.py (new)", "app/main.py"],
    "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
}

SAMPLE_SOLUTION = {
    "id": "sol-val-5678",
    "task_id": "task-val-1234",
    "task_title": "Implement Redis Caching Layer for Store Endpoint",
    "architecture_notes": "Implemented Redis caching with connection pool.",
    "files": [
        {
            "path": "app/cache.py",
            "status": "create",
            "language": "python",
            "code": "class Cache:\n    pass\n",
            "explanation": "Creates Redis cache utility.",
        },
        {
            "path": "app/main.py",
            "status": "modify",
            "language": "python",
            "code": "# updated main\n",
            "explanation": "Connects cache to main.",
        },
    ],
    "testing_guide": "Run pytest tests/test_cache.py",
    "verification_steps": ["Call GET /items twice to verify cache hit"],
    "generated_at": "2026-11-16T12:05:00+00:00",
}

SAMPLE_TEST_SUITE = {
    "id": "suite-val-9012",
    "task_id": "task-val-1234",
    "task_title": "Implement Redis Caching Layer for Store Endpoint",
    "repository": {
        "project_name": "store_api",
        "source_type": "github",
        "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
        "detected_language": "python",
        "test_framework": "pytest",
    },
    "feature_test_files": [
        {
            "path": "tests/test_feature_cache.py",
            "test_kind": "feature",
            "framework": "pytest",
            "code": "def test_cache():\n    assert True\n",
            "test_cases": [
                {
                    "name": "test_cache",
                    "test_kind": "feature",
                    "case_type": "happy_path",
                    "description": "Checks cache hit",
                    "target_criterion": "GET /items returns cached responses",
                    "expected_behavior": "Returns 200",
                }
            ],
        }
    ],
    "regression_test_files": [],
    "total_feature_tests": 1,
    "total_regression_tests": 0,
    "coverage_summary": "1 feature test",
    "execution_instructions": "pytest tests/ -v",
    "generated_at": "2026-11-16T12:10:00+00:00",
}


class TestValidationEndpoint(unittest.TestCase):
    """Integration tests for POST /tasks/validate endpoint."""

    def test_validate_endpoint_success_static_returns_not_validated(self):
        """POST /tasks/validate with valid package returns 200 with overall_verdict='NOT_VALIDATED'."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "execution_mode": "static",
        }

        resp = client.post("/tasks/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("id", data)
        self.assertEqual(data["task_id"], "task-val-1234")
        self.assertEqual(data["solution_id"], "sol-val-5678")
        self.assertEqual(data["test_suite_id"], "suite-val-9012")
        self.assertEqual(
            data["starting_commit_sha"],
            "a1b2c3d4e5f67890123456789abcdef012345678",
        )
        self.assertEqual(data["execution_mode"], "static")
        self.assertTrue(data["solution_applied_successfully"])
        self.assertEqual(data["baseline_status"], "not_run")
        self.assertEqual(data["mutation_test_status"], "not_run")
        self.assertEqual(data["overall_verdict"], "NOT_VALIDATED")
        self.assertIn("app/cache.py", data["created_files"])
        self.assertIn("app/main.py", data["modified_files"])
        self.assertTrue(any("untrusted code execution on host blocked" in r for r in data["rejection_reasons"]))

    def test_validate_endpoint_unsafe_solution_path_returns_rejected(self):
        """POST /tasks/validate rejects solution with path traversal components."""
        malicious_solution = dict(SAMPLE_SOLUTION)
        malicious_solution["files"] = [
            {
                "path": "../../etc/shadow",
                "status": "create",
                "language": "python",
                "code": "malicious",
                "explanation": "evil",
            }
        ]

        payload = {
            "task": SAMPLE_TASK,
            "solution": malicious_solution,
            "test_suite": SAMPLE_TEST_SUITE,
            "execution_mode": "static",
        }

        resp = client.post("/tasks/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["overall_verdict"], "REJECTED")
        self.assertFalse(data["solution_applied_successfully"])
        self.assertTrue(any("Solution Application Integrity Failed" in r for r in data["rejection_reasons"]))

    def test_validate_endpoint_missing_modify_file_returns_rejected(self):
        """POST /tasks/validate rejects solution when a file marked 'modify' does not exist."""
        bad_solution = dict(SAMPLE_SOLUTION)
        bad_solution["files"] = [
            {
                "path": "app/nonexistent_file.py",
                "status": "modify",
                "language": "python",
                "code": "# mod",
                "explanation": "mod",
            }
        ]

        payload = {
            "task": SAMPLE_TASK,
            "solution": bad_solution,
            "test_suite": SAMPLE_TEST_SUITE,
            "execution_mode": "static",
        }

        resp = client.post("/tasks/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["overall_verdict"], "REJECTED")
        self.assertFalse(data["solution_applied_successfully"])
        self.assertTrue(any("does not exist" in r for r in data["rejection_reasons"]))

    def test_validate_endpoint_harbor_mode_without_container_returns_not_validated(self):
        """POST /tasks/validate in harbor mode returns NOT_VALIDATED without container runtime."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "execution_mode": "harbor",
        }

        resp = client.post("/tasks/validate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["overall_verdict"], "NOT_VALIDATED")
        self.assertEqual(data["execution_mode"], "harbor")

    def test_validate_endpoint_invalid_request_returns_422(self):
        """POST /tasks/validate returns 422 when required fields are missing."""
        resp = client.post("/tasks/validate", json={"task": {"title": "incomplete"}})
        self.assertEqual(resp.status_code, 422)

    @patch("app.services.validation_service.validate_task_package")
    def test_validate_endpoint_unexpected_error_returns_500(self, mock_validate):
        """POST /tasks/validate returns 500 when an unexpected internal exception occurs."""
        mock_validate.side_effect = Exception("Internal crash")
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "execution_mode": "static",
        }
        resp = client.post("/tasks/validate", json=payload)
        self.assertEqual(resp.status_code, 500)
        self.assertIn("Unexpected error", resp.json()["detail"])

    def test_existing_endpoints_compatibility(self):
        """Verifies that existing /health and /tasks/ endpoints remain unbroken."""
        resp_health = client.get("/health")
        self.assertEqual(resp_health.status_code, 200)

        resp_tasks = client.get("/tasks/")
        self.assertEqual(resp_tasks.status_code, 200)


if __name__ == "__main__":
    unittest.main()
