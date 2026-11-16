"""
Unit tests for Test Suite Schemas — Day 7 Step 1.

Tests validation of TestCase, TestFile, RepositoryMetadata, TestSuiteResponse,
and TestSuiteRequest schemas, verifying strict feature/regression separation
and starting commit SHA version tracking.
"""

import unittest
from pydantic import ValidationError

from app.schemas.repo import RepoAnalysisResponse
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import (
    RepositoryMetadata,
    TestCase,
    TestFile,
    TestSuiteRequest,
    TestSuiteResponse,
)


def _make_sample_task() -> TaskResponse:
    """Helper to build a valid TaskResponse for schema tests."""
    return TaskResponse(
        id="task-1234-abcd",
        topic="Codebase: store_api (Redis caching)",
        difficulty="medium",
        language="python",
        category="backend",
        title="Add Redis Caching to Store Endpoint",
        description="Cache database responses using Redis to reduce latency.",
        requirements=["Use redis-py connection pool", "Cache with 60s TTL"],
        acceptance_criteria=["GET /items returns cached results", "Cache expires after 60s"],
        generated_at="2026-11-16T12:00:00+00:00",
        project_name="store_api",
        relevant_files=["app/cache.py (new)", "app/main.py"],
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
    )


def _make_sample_solution(task: TaskResponse) -> SolutionResponse:
    """Helper to build a valid SolutionResponse."""
    return SolutionResponse(
        id="sol-5678-efgh",
        task_id=task.id,
        task_title=task.title,
        architecture_notes="Implemented Redis caching using connection pool.",
        files=[
            SolutionFile(
                path="app/cache.py",
                status="create",
                language="python",
                code="import redis\n\ndef get_cache(): pass",
                explanation="Creates Redis connection utility.",
            )
        ],
        testing_guide="Run pytest tests/test_cache.py",
        verification_steps=["Call GET /items twice to verify cache hit"],
        generated_at="2026-11-16T12:05:00+00:00",
    )


class TestTestSuiteSchemas(unittest.TestCase):
    """Unit tests for the Test Suite Pydantic models."""

    # ── Feature Test Definitions ────────────────────────────────────

    def test_valid_feature_test_case(self):
        """TestCase with test_kind='feature' and various case_types validates cleanly."""
        case = TestCase(
            name="test_cache_hit_returns_cached_item",
            test_kind="feature",
            case_type="happy_path",
            description="Verifies that accessing an existing cached key returns the data without hitting the DB.",
            target_criterion="GET /items returns cached results",
            expected_behavior="Returns dict matching cached data with status 200",
        )
        self.assertEqual(case.test_kind, "feature")
        self.assertEqual(case.case_type, "happy_path")
        self.assertTrue(case.id)
        self.assertEqual(case.target_criterion, "GET /items returns cached results")

    def test_feature_test_case_types(self):
        """All supported feature case_types are accepted."""
        valid_types = ["happy_path", "edge_case", "invalid_input", "error_handling", "acceptance_criterion"]
        for ctype in valid_types:
            case = TestCase(
                name=f"test_{ctype}",
                test_kind="feature",
                case_type=ctype,
                description=f"Testing {ctype}",
                expected_behavior="Expected outcome",
            )
            self.assertEqual(case.case_type, ctype)

    def test_valid_feature_test_file(self):
        """TestFile containing feature test cases validates properly."""
        test_case = TestCase(
            name="test_ttl_expiry",
            test_kind="feature",
            case_type="edge_case",
            description="Verifies keys expire after TTL",
            expected_behavior="Key is evicted",
        )
        file = TestFile(
            path="tests/test_cache.py",
            test_kind="feature",
            framework="pytest",
            code="import pytest\n\ndef test_ttl_expiry(): assert True",
            test_cases=[test_case],
        )
        self.assertEqual(file.path, "tests/test_cache.py")
        self.assertEqual(file.test_kind, "feature")
        self.assertEqual(len(file.test_cases), 1)

    # ── Regression Test Definitions ─────────────────────────────────

    def test_valid_regression_test_definition(self):
        """TestCase and TestFile with test_kind='regression' validate correctly."""
        reg_case = TestCase(
            name="test_existing_store_checkout_flow",
            test_kind="regression",
            case_type="regression_check",
            description="Ensures existing store checkout endpoint remains unaffected by caching additions.",
            target_criterion="Pre-existing checkout behavior preserved",
            expected_behavior="Order is placed successfully with status 201",
        )
        reg_file = TestFile(
            path="tests/test_checkout_regression.py",
            test_kind="regression",
            framework="pytest",
            code="def test_existing_store_checkout_flow(): assert True",
            test_cases=[reg_case],
        )
        self.assertEqual(reg_case.test_kind, "regression")
        self.assertEqual(reg_case.case_type, "regression_check")
        self.assertEqual(reg_file.test_kind, "regression")
        self.assertEqual(len(reg_file.test_cases), 1)

    # ── Invalid Categories & Missing Fields ─────────────────────────

    def test_invalid_test_kind_raises_validation_error(self):
        """test_kind other than 'feature' or 'regression' must raise ValidationError."""
        with self.assertRaises(ValidationError):
            TestCase(
                name="test_invalid_kind",
                test_kind="performance",  # Invalid
                case_type="happy_path",
                description="desc",
                expected_behavior="assert",
            )

    def test_invalid_case_type_raises_validation_error(self):
        """case_type not in TestCaseType literal raises ValidationError."""
        with self.assertRaises(ValidationError):
            TestCase(
                name="test_bad_type",
                test_kind="feature",
                case_type="unknown_type",  # Invalid
                description="desc",
                expected_behavior="assert",
            )

    def test_missing_required_fields_in_test_case(self):
        """Missing name, description, or expected_behavior raises ValidationError."""
        with self.assertRaises(ValidationError):
            TestCase(
                test_kind="feature",
                case_type="happy_path",
                # missing name, description, expected_behavior
            )

    def test_missing_required_fields_in_test_file(self):
        """Missing path, test_kind, or code in TestFile raises ValidationError."""
        with self.assertRaises(ValidationError):
            TestFile(
                path="tests/test.py",
                # missing test_kind, code
            )

    # ── Metadata Validation & Version Tracking ──────────────────────

    def test_repository_metadata_with_commit_sha(self):
        """RepositoryMetadata captures starting commit SHA, source type, and test framework."""
        meta = RepositoryMetadata(
            project_name="store_api",
            source_type="github",
            starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
            detected_language="python",
            detected_frameworks=["FastAPI", "Redis"],
            test_framework="pytest",
            test_framework_config_file="pytest.ini",
            existing_test_files=["tests/test_main.py", "tests/test_users.py"],
            environment_info={"python_version": "3.11", "pip_requirements": "requirements.txt"},
        )
        self.assertEqual(meta.project_name, "store_api")
        self.assertEqual(meta.source_type, "github")
        self.assertEqual(meta.starting_commit_sha, "a1b2c3d4e5f67890123456789abcdef012345678")
        self.assertEqual(meta.test_framework, "pytest")
        self.assertEqual(len(meta.existing_test_files), 2)
        self.assertEqual(meta.environment_info["python_version"], "3.11")

    def test_repository_metadata_invalid_source_type(self):
        """Invalid source_type raises ValidationError."""
        with self.assertRaises(ValidationError):
            RepositoryMetadata(
                project_name="repo",
                source_type="ftp",  # Invalid
            )

    def test_repository_metadata_defaults(self):
        """RepositoryMetadata provides sensible defaults when optional fields are omitted."""
        meta = RepositoryMetadata(project_name="minimal_repo")
        self.assertEqual(meta.source_type, "unknown")
        self.assertIsNone(meta.starting_commit_sha)
        self.assertEqual(meta.detected_language, "python")
        self.assertEqual(meta.detected_frameworks, [])
        self.assertEqual(meta.test_framework, "pytest")
        self.assertEqual(meta.existing_test_files, [])

    # ── Test Suite Response: Feature vs Regression Separation ───────

    def test_test_suite_response_valid(self):
        """TestSuiteResponse validates full test suite and strictly separates feature & regression tests."""
        feat_case = TestCase(
            name="test_cache_hit",
            test_kind="feature",
            case_type="happy_path",
            description="Cache hit test",
            expected_behavior="Cached value returned",
        )
        feat_file = TestFile(
            path="tests/test_feature_cache.py",
            test_kind="feature",
            code="def test_cache_hit(): assert True",
            test_cases=[feat_case],
        )

        reg_case = TestCase(
            name="test_user_login",
            test_kind="regression",
            case_type="regression_check",
            description="User login test",
            expected_behavior="User logs in without error",
        )
        reg_file = TestFile(
            path="tests/test_regression_auth.py",
            test_kind="regression",
            code="def test_user_login(): assert True",
            test_cases=[reg_case],
        )

        response = TestSuiteResponse(
            id="suite-123",
            task_id="task-1234-abcd",
            task_title="Add Redis Caching",
            repository=RepositoryMetadata(
                project_name="store_api",
                starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
            ),
            feature_test_files=[feat_file],
            regression_test_files=[reg_file],
            total_feature_tests=1,
            total_regression_tests=1,
            coverage_summary="1 feature test (happy path) + 1 regression test (auth)",
            execution_instructions="pytest tests/ -v",
            generated_at="2026-11-16T12:10:00+00:00",
        )

        self.assertEqual(response.task_id, "task-1234-abcd")
        self.assertEqual(len(response.feature_test_files), 1)
        self.assertEqual(len(response.regression_test_files), 1)
        self.assertEqual(response.feature_test_files[0].test_kind, "feature")
        self.assertEqual(response.regression_test_files[0].test_kind, "regression")
        self.assertEqual(response.total_feature_tests, 1)
        self.assertEqual(response.total_regression_tests, 1)
        self.assertEqual(
            response.repository.starting_commit_sha,
            "a1b2c3d4e5f67890123456789abcdef012345678",
        )

    def test_test_suite_response_rejects_negative_test_counts(self):
        """Negative counts for total_feature_tests or total_regression_tests fail validation."""
        with self.assertRaises(ValidationError):
            TestSuiteResponse(
                id="suite-123",
                task_id="task-123",
                task_title="title",
                repository=RepositoryMetadata(project_name="repo"),
                total_feature_tests=-1,  # ge=0 violation
                coverage_summary="summary",
                execution_instructions="run",
                generated_at="2026-11-16T12:00:00Z",
            )

    # ── Compatibility with Existing Schemas ─────────────────────────

    def test_test_suite_request_compatibility(self):
        """TestSuiteRequest integrates smoothly with TaskResponse, SolutionResponse, and RepoAnalysisResponse."""
        task = _make_sample_task()
        solution = _make_sample_solution(task)
        analysis = RepoAnalysisResponse(
            project_name="store_api",
            source_type="github",
            detected_languages=["python"],
            detected_frameworks=["fastapi"],
            commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
        )

        request = TestSuiteRequest(
            task=task,
            solution=solution,
            repo_analysis=analysis,
            preferred_framework="pytest",
        )

        self.assertEqual(request.task.id, task.id)
        self.assertEqual(request.solution.id, solution.id)
        self.assertEqual(request.repo_analysis.project_name, "store_api")
        self.assertEqual(request.repo_analysis.commit_sha, "a1b2c3d4e5f67890123456789abcdef012345678")
        self.assertEqual(request.preferred_framework, "pytest")

    def test_test_suite_request_minimal(self):
        """TestSuiteRequest succeeds with only the required task field."""
        task = _make_sample_task()
        request = TestSuiteRequest(task=task)

        self.assertEqual(request.task.id, task.id)
        self.assertIsNone(request.solution)
        self.assertIsNone(request.repo_analysis)
        self.assertIsNone(request.starting_commit_sha)
        self.assertIsNone(request.preferred_framework)

    def test_task_response_backward_compatibility_with_commit_sha(self):
        """TaskResponse backward compatibility: instantiates with or without starting_commit_sha."""
        task_without_sha = TaskResponse(
            id="t1",
            topic="topic",
            difficulty="easy",
            language="python",
            category="backend",
            title="title",
            description="desc",
            requirements=[],
            acceptance_criteria=[],
            generated_at="2026-11-16T12:00:00Z",
        )
        self.assertIsNone(task_without_sha.starting_commit_sha)

        task_with_sha = TaskResponse(
            id="t2",
            topic="topic",
            difficulty="easy",
            language="python",
            category="backend",
            title="title",
            description="desc",
            requirements=[],
            acceptance_criteria=[],
            generated_at="2026-11-16T12:00:00Z",
            starting_commit_sha="abc1234def",
        )
        self.assertEqual(task_with_sha.starting_commit_sha, "abc1234def")

    def test_repo_analysis_response_backward_compatibility_with_commit_sha(self):
        """RepoAnalysisResponse backward compatibility: instantiates with or without commit_sha."""
        repo_without_sha = RepoAnalysisResponse(
            project_name="my_proj",
            source_type="zip",
        )
        self.assertIsNone(repo_without_sha.commit_sha)

        repo_with_sha = RepoAnalysisResponse(
            project_name="my_proj",
            source_type="github",
            commit_sha="fedcba9876543210",
        )
        self.assertEqual(repo_with_sha.commit_sha, "fedcba9876543210")


if __name__ == "__main__":
    unittest.main(verbosity=2)
