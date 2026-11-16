"""
Integration tests for POST /tasks/tests endpoint — Day 7 Step 3.

Verifies end-to-end API behavior, schema validation, feature/regression separation,
starting commit SHA preservation, error handling, and backward compatibility.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ── Reusable Test Data ──────────────────────────────────────────────

SAMPLE_TASK = {
    "id": "task-uuid-1234",
    "topic": "Codebase: store_api (Redis caching)",
    "difficulty": "medium",
    "language": "python",
    "category": "backend",
    "title": "Implement Redis Caching Layer for Store Endpoint",
    "description": "Add a Redis cache with 60s TTL to /items endpoint.",
    "requirements": [
        "Use redis-py connection pool",
        "Cache /items responses with 60s TTL",
    ],
    "acceptance_criteria": [
        "GET /items returns cached responses on second call",
        "When Redis is down, endpoint falls back gracefully without 500",
    ],
    "generated_at": "2026-11-16T12:00:00+00:00",
    "project_name": "store_api",
    "relevant_files": ["app/cache.py (new)", "app/main.py"],
    "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
}

SAMPLE_SOLUTION = {
    "id": "sol-uuid-5678",
    "task_id": "task-uuid-1234",
    "task_title": "Implement Redis Caching Layer for Store Endpoint",
    "architecture_notes": "Implemented Redis caching with connection pool.",
    "files": [
        {
            "path": "app/cache.py",
            "status": "create",
            "language": "python",
            "code": "import redis\n\ndef get_cache(): pass",
            "explanation": "Creates Redis connection utility.",
        }
    ],
    "testing_guide": "Run pytest tests/test_cache.py",
    "verification_steps": ["Call GET /items twice to verify cache hit"],
    "generated_at": "2026-11-16T12:05:00+00:00",
}

VALID_GEMINI_TEST_JSON = json.dumps({
    "coverage_summary": "Feature tests for cache hit/fallback and regression checks for checkout.",
    "execution_instructions": "pytest tests/ -v",
    "feature_test_files": [
        {
            "path": "tests/test_feature_cache.py",
            "framework": "pytest",
            "code": (
                "import pytest\nfrom unittest.mock import patch\n\n"
                "def test_cache_hit():\n"
                "    with patch('app.cache.redis_client') as m:\n"
                "        m.get.return_value = '{\"id\": 1}'\n"
                "        assert True\n"
            ),
            "test_cases": [
                {
                    "name": "test_cache_hit",
                    "case_type": "happy_path",
                    "description": "Verifies data served from cache",
                    "target_criterion": "GET /items returns cached responses on second call",
                    "expected_behavior": "Returns deserialized item",
                }
            ],
        }
    ],
    "regression_test_files": [
        {
            "path": "tests/test_regression_checkout.py",
            "framework": "pytest",
            "code": (
                "def test_checkout_unaffected():\n"
                "    assert 1 + 1 == 2\n"
            ),
            "test_cases": [
                {
                    "name": "test_checkout_unaffected",
                    "case_type": "regression_check",
                    "description": "Ensures checkout flow is not broken",
                    "target_criterion": "Existing checkout workflow preserved",
                    "expected_behavior": "Checkout succeeds",
                }
            ],
        }
    ],
})


class TestTestEndpoint(unittest.TestCase):
    """Integration tests for POST /tasks/tests endpoint."""

    @patch("app.services.test_service.GEMINI_API_KEY", "fake-test-key")
    @patch("app.services.test_service.genai.Client")
    def test_generate_tests_endpoint_success(self, mock_client_cls):
        """POST /tasks/tests returns 201 with a valid TestSuiteResponse."""
        mock_response = MagicMock()
        mock_response.text = VALID_GEMINI_TEST_JSON
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
            "preferred_framework": "pytest",
        }

        resp = client.post("/tasks/tests", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()

        self.assertIn("id", data)
        self.assertEqual(data["task_id"], SAMPLE_TASK["id"])
        self.assertEqual(data["task_title"], SAMPLE_TASK["title"])
        self.assertIn("repository", data)
        self.assertEqual(
            data["repository"]["starting_commit_sha"],
            "a1b2c3d4e5f67890123456789abcdef012345678",
        )
        self.assertEqual(data["total_feature_tests"], 1)
        self.assertEqual(data["total_regression_tests"], 1)
        self.assertEqual(len(data["feature_test_files"]), 1)
        self.assertEqual(len(data["regression_test_files"]), 1)
        self.assertEqual(data["feature_test_files"][0]["test_kind"], "feature")
        self.assertEqual(data["regression_test_files"][0]["test_kind"], "regression")

    @patch("app.services.test_service.GEMINI_API_KEY", "fake-test-key")
    @patch("app.services.test_service.genai.Client")
    def test_optional_solution_omitted(self, mock_client_cls):
        """POST /tasks/tests succeeds when solution is omitted."""
        mock_response = MagicMock()
        mock_response.text = VALID_GEMINI_TEST_JSON
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        payload = {"task": SAMPLE_TASK}
        resp = client.post("/tasks/tests", json=payload)

        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["task_id"], SAMPLE_TASK["id"])

    @patch("app.services.test_service.GEMINI_API_KEY", "fake-test-key")
    @patch("app.services.test_service.genai.Client")
    def test_repo_analysis_context_integration(self, mock_client_cls):
        """POST /tasks/tests integrates repo_analysis context and preserves commit SHA."""
        mock_response = MagicMock()
        mock_response.text = VALID_GEMINI_TEST_JSON
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        payload = {
            "task": SAMPLE_TASK,
            "repo_analysis": {
                "project_name": "store_api",
                "source_type": "github",
                "detected_languages": ["python"],
                "detected_frameworks": ["FastAPI"],
                "file_count": 10,
                "folder_structure": ["app", "tests"],
                "analysis_status": "completed",
                "commit_sha": "commit-9999-sha",
            },
        }

        resp = client.post("/tasks/tests", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["repository"]["commit_sha"] if "commit_sha" in data["repository"] else data["repository"]["starting_commit_sha"], "commit-9999-sha")

    @patch("app.services.test_service.GEMINI_API_KEY", "")
    def test_missing_api_key_returns_503(self):
        """POST /tasks/tests returns 503 when GEMINI_API_KEY is not set."""
        resp = client.post("/tasks/tests", json={"task": SAMPLE_TASK})
        self.assertEqual(resp.status_code, 503)
        self.assertIn("GEMINI_API_KEY", resp.json()["detail"])

    @patch("app.services.test_service.GEMINI_API_KEY", "fake-test-key")
    @patch("app.services.test_service.genai.Client")
    def test_gemini_api_failure_returns_502(self, mock_client_cls):
        """POST /tasks/tests returns 502 when Gemini raises an exception."""
        mock_client_cls.return_value.models.generate_content.side_effect = Exception(
            "Service overloaded"
        )
        resp = client.post("/tasks/tests", json={"task": SAMPLE_TASK})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("Gemini API request failed", resp.json()["detail"])

    @patch("app.services.test_service.GEMINI_API_KEY", "fake-test-key")
    @patch("app.services.test_service.genai.Client")
    def test_invalid_gemini_output_returns_502(self, mock_client_cls):
        """POST /tasks/tests returns 502 when Gemini returns invalid JSON."""
        mock_response = MagicMock()
        mock_response.text = "NOT JSON"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        resp = client.post("/tasks/tests", json={"task": SAMPLE_TASK})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("not valid JSON", resp.json()["detail"])

    def test_invalid_request_body_returns_422(self):
        """POST /tasks/tests returns 422 when required task is missing or invalid."""
        resp = client.post("/tasks/tests", json={"task": {"title": "incomplete"}})
        self.assertEqual(resp.status_code, 422)

    def test_existing_endpoints_unbroken(self):
        """Confirms that GET /health and GET /tasks/ still return expected responses."""
        resp_health = client.get("/health")
        self.assertEqual(resp_health.status_code, 200)

        resp_list = client.get("/tasks/")
        self.assertEqual(resp_list.status_code, 200)


if __name__ == "__main__":
    unittest.main()
