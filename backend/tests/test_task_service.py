"""
Unit tests for task_service.generate_task().

All tests mock the Gemini client — no real API calls, no credits consumed.
Run with:  python -m unittest discover -s tests  (from backend/ directory)
"""
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Make sure backend/ is on the path when running from tests/ or backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas.task import TaskRequest, TaskResponse


# ── Helpers ────────────────────────────────────────────────────────

def _make_request(**kwargs) -> TaskRequest:
    defaults = dict(topic="REST API rate limiting", difficulty="medium",
                    language="python", category="backend")
    defaults.update(kwargs)
    return TaskRequest(**defaults)


def _mock_gemini_response(payload: dict) -> MagicMock:
    """Return a mock that looks like a Gemini GenerateContentResponse."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(payload)
    return mock_resp


VALID_GEMINI_PAYLOAD = {
    "title": "Implement Token-Bucket Rate Limiting Middleware",
    "description": (
        "The public API is receiving excessive traffic from certain clients, "
        "causing degraded performance for legitimate users. "
        "You need to implement a token-bucket rate limiting middleware "
        "that throttles requests per API key.\n\n"
        "The middleware should integrate cleanly with the existing FastAPI "
        "application and be configurable per route."
    ),
    "requirements": [
        "Implement a token-bucket algorithm that allows bursting up to 2x the base rate",
        "Store rate limit state in an in-memory dictionary keyed by API key",
        "Return HTTP 429 with a Retry-After header when the limit is exceeded",
        "Expose config options: requests_per_minute and burst_multiplier",
    ],
    "acceptance_criteria": [
        "Given a client sends 60 requests/min, when the limit is 30 rpm, "
        "then requests 31+ receive HTTP 429",
        "Given a 429 response, then the Retry-After header contains a positive integer",
        "Given no API key header, then all requests share a single anonymous bucket",
    ],
}


# ── Test cases ────────────────────────────────────────────────────

class TestGenerateTaskSuccess(unittest.TestCase):
    """Happy-path: Gemini returns valid JSON."""

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_returns_task_response(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_GEMINI_PAYLOAD)
        )
        from app.services import task_service
        result = task_service.generate_task(_make_request())
        self.assertIsInstance(result, TaskResponse)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_response_fields_populated(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_GEMINI_PAYLOAD)
        )
        from app.services import task_service
        result = task_service.generate_task(_make_request(topic="rate limiting"))
        self.assertEqual(result.topic, "rate limiting")
        self.assertEqual(result.title, VALID_GEMINI_PAYLOAD["title"])
        self.assertEqual(result.difficulty, "medium")
        self.assertEqual(result.language, "python")
        self.assertEqual(result.category, "backend")

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_response_has_unique_id(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_GEMINI_PAYLOAD)
        )
        from app.services import task_service
        r1 = task_service.generate_task(_make_request())
        r2 = task_service.generate_task(_make_request())
        self.assertNotEqual(r1.id, r2.id)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_response_has_requirements_and_criteria(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_GEMINI_PAYLOAD)
        )
        from app.services import task_service
        result = task_service.generate_task(_make_request())
        self.assertIsInstance(result.requirements, list)
        self.assertGreater(len(result.requirements), 0)
        self.assertIsInstance(result.acceptance_criteria, list)
        self.assertGreater(len(result.acceptance_criteria), 0)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_generated_at_is_iso_format(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_GEMINI_PAYLOAD)
        )
        from app.services import task_service
        result = task_service.generate_task(_make_request())
        # Must parse without raising
        from datetime import datetime
        datetime.fromisoformat(result.generated_at)


class TestGenerateTaskMissingKey(unittest.TestCase):
    """API key missing — should raise ValueError before touching Gemini."""

    @patch("app.services.task_service.GEMINI_API_KEY", "")
    def test_raises_value_error_when_key_missing(self):
        from app.services import task_service
        with self.assertRaises(ValueError) as ctx:
            task_service.generate_task(_make_request())
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


class TestGenerateTaskGeminiFailure(unittest.TestCase):
    """Gemini API throws an exception — should wrap in RuntimeError."""

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_raises_runtime_error_on_api_failure(self, MockClient):
        MockClient.return_value.models.generate_content.side_effect = (
            Exception("503 Service Unavailable")
        )
        from app.services import task_service
        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task(_make_request())
        self.assertIn("Gemini API request failed", str(ctx.exception))


class TestGenerateTaskBadJSON(unittest.TestCase):
    """Gemini returns malformed JSON — should raise RuntimeError."""

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_raises_runtime_error_on_invalid_json(self, MockClient):
        bad = MagicMock()
        bad.text = "Sure! Here is a task: { not valid json }"
        MockClient.return_value.models.generate_content.return_value = bad
        from app.services import task_service
        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task(_make_request())
        self.assertIn("not valid JSON", str(ctx.exception))


class TestGenerateTaskMissingFields(unittest.TestCase):
    """Gemini returns JSON but with missing required fields."""

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_raises_runtime_error_on_missing_fields(self, MockClient):
        incomplete = {"title": "Some task"}   # missing description, requirements, criteria
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(incomplete)
        )
        from app.services import task_service
        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task(_make_request())
        self.assertIn("missing expected fields", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
