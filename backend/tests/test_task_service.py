"""
Unit tests for task_service.generate_task() and task_service.generate_task_from_repo().

All tests mock the Gemini client — no real API calls, no credits consumed.
Run with:  python -m unittest discover -s tests  (from backend/ directory)
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make sure backend/ is on the path when running from tests/ or backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas.repo import RepoAnalysisResponse
from app.schemas.task import RepoTaskRequest, TaskRequest, TaskResponse


# ── Helpers ────────────────────────────────────────────────────────

def _make_request(**kwargs) -> TaskRequest:
    defaults = dict(
        topic="REST API rate limiting",
        difficulty="medium",
        language="python",
        category="backend",
    )
    defaults.update(kwargs)
    return TaskRequest(**defaults)


def _make_repo_analysis(**kwargs) -> RepoAnalysisResponse:
    defaults = dict(
        project_name="fastapi-task-service",
        source_type="github",
        detected_languages=["Python"],
        detected_frameworks=["FastAPI", "Pydantic"],
        file_count=12,
        folder_structure=["app", "app/routers", "tests"],
        readme_summary="FastAPI background task service",
        analysis_status="completed",
    )
    defaults.update(kwargs)
    return RepoAnalysisResponse(**defaults)


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

VALID_REPO_GEMINI_PAYLOAD = {
    "title": "Add Distributed Redis Rate Limiting to Tasks Router",
    "description": (
        "The current FastAPI task service processes all requests in-memory. "
        "Integrate Redis-based throttling for the /tasks/generate endpoint "
        "to ensure high availability across multiple worker replicas."
    ),
    "requirements": [
        "Create app/core/redis.py providing an async Redis connection pool",
        "Implement rate limiting dependency in app/routers/tasks.py",
        "Return standard 429 Too Many Requests response with retry headers",
    ],
    "acceptance_criteria": [
        "Given 10 requests within 60s, then all 10 return 200 OK",
        "Given the 11th request in the same window, then return 429 Too Many Requests",
    ],
    "relevant_files": [
        "app/routers/tasks.py",
        "app/core/redis.py (new)",
        "tests/test_rate_limit.py (new)",
    ],
}


# ── Topic-based Task Tests (generate_task) ──────────────────────────

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
        MockClient.return_value.models.generate_content.side_effect = Exception(
            "503 Service Unavailable"
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
        incomplete = {"title": "Some task"}
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(incomplete)
        )
        from app.services import task_service

        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task(_make_request())
        self.assertIn("missing expected fields", str(ctx.exception))


# ── Contextual Task Tests (generate_task_from_repo) ─────────────────

class TestGenerateTaskFromRepo(unittest.TestCase):
    """Tests for repository-grounded contextual task generation."""

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_successful_repo_task_generation(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_REPO_GEMINI_PAYLOAD)
        )
        from app.services import task_service

        analysis = _make_repo_analysis()
        options = RepoTaskRequest(difficulty="hard", focus_area="Redis caching")

        result = task_service.generate_task_from_repo(analysis, options)

        self.assertIsInstance(result, TaskResponse)
        self.assertEqual(result.project_name, "fastapi-task-service")
        self.assertEqual(result.difficulty, "hard")
        self.assertEqual(result.title, VALID_REPO_GEMINI_PAYLOAD["title"])
        self.assertIn("Codebase: fastapi-task-service", result.topic)
        self.assertIn("Redis caching", result.topic)
        self.assertEqual(len(result.relevant_files), 3)
        self.assertIn("app/routers/tasks.py", result.relevant_files)
        self.assertIn("app/core/redis.py (new)", result.relevant_files)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_prompt_includes_repo_context(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_REPO_GEMINI_PAYLOAD)
        )
        from app.services import task_service

        analysis = _make_repo_analysis(
            project_name="my-ecommerce-app",
            detected_languages=["TypeScript", "CSS"],
            detected_frameworks=["React", "Next.js"],
            folder_structure=["src", "src/components", "src/pages"],
        )
        options = RepoTaskRequest(difficulty="easy", focus_area="checkout button")

        task_service.generate_task_from_repo(analysis, options)

        # Inspect the prompt passed to Gemini generate_content
        call_args = MockClient.return_value.models.generate_content.call_args
        prompt_sent = call_args.kwargs.get("contents") or call_args[1].get("contents")

        self.assertIn("my-ecommerce-app", prompt_sent)
        self.assertIn("TypeScript", prompt_sent)
        self.assertIn("React", prompt_sent)
        self.assertIn("src/components", prompt_sent)
        self.assertIn("checkout button", prompt_sent)
        self.assertIn("easy", prompt_sent)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_default_options_when_omitted(self, MockClient):
        MockClient.return_value.models.generate_content.return_value = (
            _mock_gemini_response(VALID_REPO_GEMINI_PAYLOAD)
        )
        from app.services import task_service

        analysis = _make_repo_analysis()
        result = task_service.generate_task_from_repo(analysis, options=None)

        self.assertEqual(result.difficulty, "medium")
        self.assertEqual(result.project_name, "fastapi-task-service")

    @patch("app.services.task_service.GEMINI_API_KEY", "")
    def test_missing_api_key_raises_value_error(self):
        from app.services import task_service

        analysis = _make_repo_analysis()
        with self.assertRaises(ValueError) as ctx:
            task_service.generate_task_from_repo(analysis)
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_api_failure_raises_runtime_error(self, MockClient):
        MockClient.return_value.models.generate_content.side_effect = Exception("API Quota Exceeded")
        from app.services import task_service

        analysis = _make_repo_analysis()
        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task_from_repo(analysis)
        self.assertIn("Gemini API request failed", str(ctx.exception))

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_malformed_json_raises_runtime_error(self, MockClient):
        bad = MagicMock()
        bad.text = "Here is your task: not JSON"
        MockClient.return_value.models.generate_content.return_value = bad
        from app.services import task_service

        analysis = _make_repo_analysis()
        with self.assertRaises(RuntimeError) as ctx:
            task_service.generate_task_from_repo(analysis)
        self.assertIn("not valid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
