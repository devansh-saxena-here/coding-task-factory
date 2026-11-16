"""
Unit tests for test_service.generate_test_suite() — Day 7 Step 2 (Stream B).

All tests mock the Gemini client — zero API calls, deterministic assertions,
and zero code execution.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app.schemas.repo import RepoAnalysisResponse
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestSuiteResponse
from app.services import test_service


def _make_sample_task() -> TaskResponse:
    """Helper to build a valid TaskResponse."""
    return TaskResponse(
        id="task-uuid-1234",
        topic="Codebase: store_api (Redis caching)",
        difficulty="medium",
        language="python",
        category="backend",
        title="Implement Redis Caching Layer for Store Endpoint",
        description="Add a Redis cache with 60s TTL to /items endpoint.",
        requirements=[
            "Use redis-py connection pool",
            "Cache /items responses with 60s TTL",
        ],
        acceptance_criteria=[
            "GET /items returns cached responses on second call",
            "When Redis is down, endpoint falls back gracefully without 500",
        ],
        generated_at="2026-11-16T12:00:00+00:00",
        project_name="store_api",
        relevant_files=["app/cache.py (new)", "app/main.py"],
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
    )


VALID_GEMINI_OUTPUT = {
    "coverage_summary": "Comprehensive test suite covering cache hits, TTL eviction, fallback on connection error, and regression checks on existing checkout endpoint.",
    "execution_instructions": "pytest tests/ -v",
    "feature_test_files": [
        {
            "path": "tests/test_feature_cache.py",
            "framework": "pytest",
            "code": (
                "import pytest\nfrom unittest.mock import MagicMock, patch\nfrom app.cache import get_cached_item\n\n"
                "def test_cache_hit_returns_cached_data():\n"
                "    with patch('app.cache.redis_client') as mock_redis:\n"
                "        mock_redis.get.return_value = '{\"id\": 1}'\n"
                "        val = get_cached_item('item_1')\n"
                "        assert val == {'id': 1}\n\n"
                "def test_redis_failure_falls_back_gracefully():\n"
                "    with patch('app.cache.redis_client') as mock_redis:\n"
                "        mock_redis.get.side_effect = Exception('Connection refused')\n"
                "        val = get_cached_item('item_1')\n"
                "        assert val is None\n"
            ),
            "test_cases": [
                {
                    "name": "test_cache_hit_returns_cached_data",
                    "case_type": "happy_path",
                    "description": "Verifies data served from cache when present",
                    "target_criterion": "GET /items returns cached responses on second call",
                    "expected_behavior": "Returns deserialized item dictionary",
                },
                {
                    "name": "test_redis_failure_falls_back_gracefully",
                    "case_type": "error_handling",
                    "description": "Ensures Redis connection drop does not crash caller",
                    "target_criterion": "When Redis is down, endpoint falls back gracefully without 500",
                    "expected_behavior": "Returns None instead of raising exception",
                },
            ],
        }
    ],
    "regression_test_files": [
        {
            "path": "tests/test_regression_checkout.py",
            "framework": "pytest",
            "code": (
                "from app.main import checkout\n\n"
                "def test_checkout_remains_functional():\n"
                "    res = checkout({'item_id': 1})\n"
                "    assert res['status'] == 'success'\n"
            ),
            "test_cases": [
                {
                    "name": "test_checkout_remains_functional",
                    "case_type": "regression_check",
                    "description": "Protects existing checkout endpoint functionality",
                    "target_criterion": "Existing checkout workflow preserved",
                    "expected_behavior": "Returns status success",
                }
            ],
        }
    ],
}


class TestTestService(unittest.TestCase):
    """Unit tests for test_service.generate_test_suite."""

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_successful_test_suite_generation(self, MockClient):
        """Generates a valid TestSuiteResponse from TaskResponse with feature & regression separation."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(VALID_GEMINI_OUTPUT)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        result = test_service.generate_test_suite(task)

        self.assertIsInstance(result, TestSuiteResponse)
        self.assertEqual(result.task_id, task.id)
        self.assertEqual(result.task_title, task.title)
        self.assertEqual(len(result.feature_test_files), 1)
        self.assertEqual(len(result.regression_test_files), 1)
        self.assertEqual(result.total_feature_tests, 2)
        self.assertEqual(result.total_regression_tests, 1)
        self.assertEqual(result.feature_test_files[0].test_kind, "feature")
        self.assertEqual(result.regression_test_files[0].test_kind, "regression")
        self.assertEqual(result.repository.starting_commit_sha, "a1b2c3d4e5f67890123456789abcdef012345678")
        self.assertEqual(result.execution_instructions, "pytest tests/ -v")

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_prompt_includes_requirements_criteria_and_security(self, MockClient):
        """Verifies that the prompt sent to Gemini includes untrusted-data boundary, requirements, and criteria."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(VALID_GEMINI_OUTPUT)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        test_service.generate_test_suite(task)

        call_args = MockClient.return_value.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents") or call_args[1].get("contents")

        self.assertIn("UNTRUSTED DATA", prompt)
        self.assertIn("Use redis-py connection pool", prompt)
        self.assertIn("GET /items returns cached responses", prompt)
        self.assertIn("a1b2c3d4e5f67890123456789abcdef012345678", prompt)
        self.assertIn("FEATURE TESTS", prompt)
        self.assertIn("REGRESSION CHECKS", prompt)

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_with_solution_and_repo_context(self, MockClient):
        """Test suite correctly incorporates optional solution and repository context."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(VALID_GEMINI_OUTPUT)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        solution = SolutionResponse(
            id="sol-1",
            task_id=task.id,
            task_title=task.title,
            architecture_notes="Redis connection pooling",
            files=[
                SolutionFile(
                    path="app/cache.py",
                    status="create",
                    language="python",
                    code="class Cache: pass",
                    explanation="Cache class",
                )
            ],
            testing_guide="Use pytest",
            verification_steps=["Step 1"],
            generated_at="2026-11-16T12:00:00Z",
        )
        repo_context = RepoAnalysisResponse(
            project_name="store_api",
            source_type="github",
            detected_languages=["python"],
            detected_frameworks=["FastAPI"],
            commit_sha="fedcba9876543210",
        )

        result = test_service.generate_test_suite(
            task=task,
            solution=solution,
            repository_context=repo_context,
            framework="pytest",
        )

        self.assertEqual(result.repository.project_name, "store_api")
        self.assertEqual(result.repository.starting_commit_sha, "fedcba9876543210")

    @patch("app.services.test_service.GEMINI_API_KEY", "")
    def test_missing_api_key_raises_value_error(self):
        """Missing GEMINI_API_KEY raises ValueError."""
        task = _make_sample_task()
        with self.assertRaises(ValueError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_gemini_api_failure_raises_runtime_error(self, MockClient):
        """Gemini exception raises RuntimeError."""
        MockClient.return_value.models.generate_content.side_effect = Exception("Service unavailable")
        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("Gemini API request failed", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_malformed_json_raises_runtime_error(self, MockClient):
        """Malformed JSON from Gemini raises RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.text = "This is not JSON text at all"
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("not valid JSON", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_missing_required_fields_raises_runtime_error(self, MockClient):
        """Missing required top-level keys in JSON raises RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({"coverage_summary": "Only summary"})
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("missing required fields", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_rejects_todo_placeholder_in_test_code(self, MockClient):
        """Rejects test file containing '# TODO' or placeholder comment."""
        payload = dict(VALID_GEMINI_OUTPUT)
        payload["feature_test_files"] = [
            {
                "path": "tests/test_bad.py",
                "framework": "pytest",
                "code": "def test_something():\n    # TODO: write this test\n    pass\n",
                "test_cases": [],
            }
        ]
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(payload)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("forbidden placeholder", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_rejects_empty_code_in_test_file(self, MockClient):
        """Rejects test file with empty code."""
        payload = dict(VALID_GEMINI_OUTPUT)
        payload["feature_test_files"] = [
            {
                "path": "tests/test_empty.py",
                "framework": "pytest",
                "code": "   \n",
                "test_cases": [],
            }
        ]
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(payload)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("empty code", str(ctx.exception))

    @patch("app.services.test_service.genai.Client")
    @patch("app.services.test_service.GEMINI_API_KEY", "test-api-key")
    def test_rejects_trivial_assert_true_alone(self, MockClient):
        """Rejects test file containing only trivial 'assert True'."""
        payload = dict(VALID_GEMINI_OUTPUT)
        payload["feature_test_files"] = [
            {
                "path": "tests/test_trivial.py",
                "framework": "pytest",
                "code": "assert True\n",
                "test_cases": [],
            }
        ]
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(payload)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        task = _make_sample_task()
        with self.assertRaises(RuntimeError) as ctx:
            test_service.generate_test_suite(task)
        self.assertIn("trivial dummy assertions", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
