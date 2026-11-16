"""
Unit tests for solution_service.generate_reference_solution().

All tests mock the Gemini client — no real API calls, no credits consumed.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend/ is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas.solution import SolutionResponse
from app.schemas.task import TaskResponse


def _make_sample_task() -> TaskResponse:
    return TaskResponse(
        id="987fcdeb-51a2-43d7-9012-345678901234",
        topic="Codebase: my_store (Redis inventory caching)",
        difficulty="medium",
        language="python",
        category="backend",
        title="Implement Redis Caching for Store Items Endpoint",
        description="Our store API currently queries the database on every items lookup. Implement Redis caching.",
        requirements=[
            "Add redis to requirements.txt",
            "Create a Redis connection utility in my_store/cache.py",
            "Update /items endpoint to cache responses with a 60s TTL",
        ],
        acceptance_criteria=[
            "Given a cache miss, data is fetched and stored in Redis with 60s TTL",
            "Given Redis is unreachable, endpoint falls back gracefully without 500 error",
        ],
        generated_at="2026-11-16T12:00:00+00:00",
        project_name="my_store",
        relevant_files=[
            "my_store/main.py",
            "my_store/cache.py (new)",
            "my_store/requirements.txt",
        ],
    )


VALID_SOLUTION_PAYLOAD = {
    "architecture_notes": (
        "We implement a Redis caching layer using redis-py's connection pooling. "
        "The cache helper handles serialization to JSON and gracefully catches ConnectionError "
        "so the API continues to function even if Redis experiences an outage."
    ),
    "files": [
        {
            "path": "my_store/cache.py",
            "status": "create",
            "language": "python",
            "code": (
                "import json\nimport logging\nimport redis\n\nlogger = logging.getLogger(__name__)\n"
                "pool = redis.ConnectionPool(host='localhost', port=6379, db=0)\n\n"
                "def get_cached_items(key: str):\n"
                "    try:\n"
                "        r = redis.Redis(connection_pool=pool)\n"
                "        val = r.get(key)\n"
                "        return json.loads(val) if val else None\n"
                "    except Exception as e:\n"
                "        logger.warning(f'Redis error: {e}')\n"
                "        return None\n"
            ),
            "explanation": "Creates the Redis connection utility with try/except graceful fallback.",
        },
        {
            "path": "my_store/main.py",
            "status": "modify",
            "language": "python",
            "code": (
                "from fastapi import FastAPI\nfrom my_store.cache import get_cached_items\n\napp = FastAPI()\n\n"
                "@app.get('/items')\ndef get_items():\n    cached = get_cached_items('store_items')\n"
                "    if cached is not None:\n        return cached\n    return [{'id': 1, 'name': 'Item A'}]\n"
            ),
            "explanation": "Updates the /items endpoint to check cache before returning data.",
        },
    ],
    "testing_guide": (
        "Write integration tests using fakeredis or a test Redis container. "
        "Test both cache hits, misses, and simulate connection failure."
    ),
    "verification_steps": [
        "Start a local Redis instance on port 6379.",
        "Send GET /items and verify data is returned.",
        "Check Redis using redis-cli GET store_items and verify TTL is under 60 seconds.",
        "Stop Redis service and send GET /items to confirm it still returns 200 without crashing.",
    ],
}


class TestSolutionService(unittest.TestCase):
    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_successful_solution_generation(self, MockClient):
        """Generates a valid SolutionResponse from a TaskResponse."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(VALID_SOLUTION_PAYLOAD)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        from app.services import solution_service

        task = _make_sample_task()
        result = solution_service.generate_reference_solution(task)

        self.assertIsInstance(result, SolutionResponse)
        self.assertEqual(result.task_id, task.id)
        self.assertEqual(result.task_title, task.title)
        self.assertEqual(result.architecture_notes, VALID_SOLUTION_PAYLOAD["architecture_notes"])
        self.assertEqual(len(result.files), 2)
        self.assertEqual(result.files[0].path, "my_store/cache.py")
        self.assertEqual(result.files[0].status, "create")
        self.assertEqual(result.files[1].path, "my_store/main.py")
        self.assertEqual(result.files[1].status, "modify")
        self.assertEqual(len(result.verification_steps), 4)
        self.assertTrue(result.id)
        self.assertTrue(result.generated_at)

    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_solution_prompt_includes_task_details(self, MockClient):
        """Prompt sent to Gemini includes title, requirements, criteria, and files."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(VALID_SOLUTION_PAYLOAD)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        from app.services import solution_service

        task = _make_sample_task()
        solution_service.generate_reference_solution(task)

        call_args = MockClient.return_value.models.generate_content.call_args
        prompt_sent = call_args.kwargs.get("contents") or call_args[1].get("contents")

        self.assertIn("Implement Redis Caching", prompt_sent)
        self.assertIn("Add redis to requirements.txt", prompt_sent)
        self.assertIn("Given a cache miss", prompt_sent)
        self.assertIn("my_store/cache.py (new)", prompt_sent)
        self.assertIn("my_store", prompt_sent)

    @patch("app.services.solution_service.GEMINI_API_KEY", "")
    def test_missing_api_key_raises_value_error(self):
        """Missing GEMINI_API_KEY raises ValueError."""
        from app.services import solution_service

        task = _make_sample_task()
        with self.assertRaises(ValueError) as ctx:
            solution_service.generate_reference_solution(task)
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_gemini_api_failure_raises_runtime_error(self, MockClient):
        """Gemini exception raises RuntimeError."""
        MockClient.return_value.models.generate_content.side_effect = Exception("503 Service Overloaded")
        from app.services import solution_service

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            solution_service.generate_reference_solution(task)
        self.assertIn("Gemini API request failed", str(ctx.exception))

    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_malformed_json_raises_runtime_error(self, MockClient):
        """Malformed JSON from Gemini raises RuntimeError."""
        bad_mock = MagicMock()
        bad_mock.text = "Here is your solution: not JSON"
        MockClient.return_value.models.generate_content.return_value = bad_mock
        from app.services import solution_service

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            solution_service.generate_reference_solution(task)
        self.assertIn("not valid JSON", str(ctx.exception))

    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_missing_fields_raises_runtime_error(self, MockClient):
        """Missing required top-level fields raises RuntimeError."""
        incomplete = {"architecture_notes": "Some notes"}  # Missing files, testing_guide, etc.
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(incomplete)
        MockClient.return_value.models.generate_content.return_value = mock_resp
        from app.services import solution_service

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            solution_service.generate_reference_solution(task)
        self.assertIn("missing expected fields", str(ctx.exception))

    @patch("app.services.solution_service.genai.Client")
    @patch("app.services.solution_service.GEMINI_API_KEY", "fake-test-key")
    def test_invalid_file_status_raises_runtime_error(self, MockClient):
        """Invalid file status (e.g. 'delete') raises RuntimeError."""
        payload = dict(VALID_SOLUTION_PAYLOAD)
        payload["files"] = [
            {
                "path": "app/bad.py",
                "status": "remove",  # Invalid status
                "language": "python",
                "code": "# code",
                "explanation": "# exp",
            }
        ]
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(payload)
        MockClient.return_value.models.generate_content.return_value = mock_resp
        from app.services import solution_service

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            solution_service.generate_reference_solution(task)
        self.assertIn("Invalid file specification", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
