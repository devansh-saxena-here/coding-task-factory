"""Tests for POST /tasks/solution endpoint — Day 6 Step 3."""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ── Reusable test data ──────────────────────────────────────────────

SAMPLE_TASK = {
    "id": "task-001",
    "topic": "Codebase: my-api (caching layer)",
    "title": "Implement caching layer",
    "description": "Add a Redis-backed caching layer to the API.",
    "language": "python",
    "difficulty": "medium",
    "category": "backend",
    "requirements": ["Implement cache decorator", "Support TTL expiry"],
    "acceptance_criteria": ["GET /items returns cached results", "Cache invalidates after TTL"],
    "generated_at": "2026-11-16T12:00:00+00:00",
    "project_name": "my-api",
    "relevant_files": ["app/services/cache.py", "app/core/config.py"],
}

GEMINI_SOLUTION_JSON = json.dumps({
    "architecture_notes": "Redis-backed caching with decorator pattern.",
    "files": [
        {
            "path": "app/services/cache.py",
            "status": "create",
            "language": "python",
            "code": "import redis\n\ndef cache(ttl=60):\n    pass",
            "explanation": "Cache decorator using Redis."
        }
    ],
    "testing_guide": "Run pytest tests/test_cache.py",
    "verification_steps": [
        "Start Redis server",
        "Call GET /items twice and verify second is cached"
    ],
})


class TestSolutionEndpoint(unittest.TestCase):
    """Tests for the POST /tasks/solution endpoint."""

    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-key-for-test")
    @patch("app.services.solution_service.genai.Client")
    def test_solution_endpoint_success(self, mock_client_cls):
        """POST /tasks/solution returns 201 with a valid SolutionResponse."""
        mock_response = MagicMock()
        mock_response.text = GEMINI_SOLUTION_JSON
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        resp = client.post("/tasks/solution", json={"task": SAMPLE_TASK})

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("id", body)
        self.assertEqual(body["task_id"], "task-001")
        self.assertEqual(body["task_title"], "Implement caching layer")
        self.assertIn("architecture_notes", body)
        self.assertIsInstance(body["files"], list)
        self.assertGreater(len(body["files"]), 0)
        self.assertEqual(body["files"][0]["path"], "app/services/cache.py")
        self.assertIn("testing_guide", body)
        self.assertIsInstance(body["verification_steps"], list)
        self.assertIn("generated_at", body)

    @patch("app.services.solution_service.GEMINI_API_KEY", "")
    def test_solution_endpoint_missing_api_key(self):
        """POST /tasks/solution returns 503 when GEMINI_API_KEY is empty."""
        resp = client.post("/tasks/solution", json={"task": SAMPLE_TASK})

        self.assertEqual(resp.status_code, 503)
        self.assertIn("GEMINI_API_KEY", resp.json()["detail"])

    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-key-for-test")
    @patch("app.services.solution_service.genai.Client")
    def test_solution_endpoint_gemini_api_failure(self, mock_client_cls):
        """POST /tasks/solution returns 502 when Gemini raises an exception."""
        mock_client_cls.return_value.models.generate_content.side_effect = Exception(
            "Service temporarily unavailable"
        )

        resp = client.post("/tasks/solution", json={"task": SAMPLE_TASK})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("Gemini API request failed", resp.json()["detail"])

    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-key-for-test")
    @patch("app.services.solution_service.genai.Client")
    def test_solution_endpoint_malformed_json(self, mock_client_cls):
        """POST /tasks/solution returns 502 when Gemini returns invalid JSON."""
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        resp = client.post("/tasks/solution", json={"task": SAMPLE_TASK})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("not valid JSON", resp.json()["detail"])

    def test_solution_endpoint_invalid_request_body(self):
        """POST /tasks/solution returns 422 for an invalid request body."""
        resp = client.post("/tasks/solution", json={"task": {"title": "incomplete"}})

        self.assertEqual(resp.status_code, 422)

    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-key-for-test")
    @patch("app.services.solution_service.genai.Client")
    def test_solution_endpoint_missing_fields_in_gemini_response(self, mock_client_cls):
        """POST /tasks/solution returns 502 when Gemini omits required fields."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({"architecture_notes": "partial"})
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        resp = client.post("/tasks/solution", json={"task": SAMPLE_TASK})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("missing expected fields", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
