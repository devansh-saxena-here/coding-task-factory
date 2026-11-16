"""
Unit tests for Validation Schemas — Day 8 Step 2.

Verifies typing, validation rules, verdict constraints, commit SHA propagation,
and bounded output limits.
"""

import unittest
from pydantic import ValidationError

from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestCase, TestFile, TestSuiteResponse
from app.schemas.validation import (
    TestExecutionResult,
    ValidationReport,
    ValidationRequest,
)


def _make_dummy_task() -> TaskResponse:
    return TaskResponse(
        id="task-123",
        topic="topic",
        difficulty="medium",
        language="python",
        category="backend",
        title="Title",
        description="Desc",
        requirements=["Req 1"],
        acceptance_criteria=["Crit 1"],
        generated_at="2026-11-16T12:00:00Z",
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
    )


def _make_dummy_solution() -> SolutionResponse:
    return SolutionResponse(
        id="sol-123",
        task_id="task-123",
        task_title="Title",
        architecture_notes="Notes",
        files=[
            SolutionFile(
                path="app/cache.py",
                status="create",
                language="python",
                code="class Cache: pass",
                explanation="Cache",
            )
        ],
        testing_guide="Guide",
        verification_steps=["Step 1"],
        generated_at="2026-11-16T12:00:00Z",
    )


def _make_dummy_test_suite() -> TestSuiteResponse:
    return TestSuiteResponse(
        id="suite-123",
        task_id="task-123",
        task_title="Title",
        repository=RepositoryMetadata(
            project_name="store",
            starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
        ),
        feature_test_files=[
            TestFile(
                path="tests/test_feature.py",
                test_kind="feature",
                code="def test_f(): assert True",
                test_cases=[
                    TestCase(
                        name="test_f",
                        test_kind="feature",
                        case_type="happy_path",
                        description="desc",
                        expected_behavior="assert",
                    )
                ],
            )
        ],
        regression_test_files=[],
        total_feature_tests=1,
        total_regression_tests=0,
        coverage_summary="summary",
        execution_instructions="pytest tests/ -v",
        generated_at="2026-11-16T12:00:00Z",
    )


class TestValidationSchemas(unittest.TestCase):
    """Unit tests for Validation Pydantic models."""

    def test_valid_test_execution_result(self):
        """TestExecutionResult validates with bounded output and proper status."""
        result = TestExecutionResult(
            test_file="tests/test_cache.py",
            test_kind="feature",
            exit_code=0,
            duration_ms=150,
            stdout="1 passed in 0.15s",
            stderr="",
            passed=True,
            individual_cases=[{"name": "test_cache_hit", "passed": True}],
        )
        self.assertEqual(result.test_file, "tests/test_cache.py")
        self.assertEqual(result.test_kind, "feature")
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.passed)

    def test_invalid_test_kind_in_execution_result(self):
        """Invalid test_kind raises ValidationError."""
        with self.assertRaises(ValidationError):
            TestExecutionResult(
                test_file="tests/test.py",
                test_kind="unsupported_kind",  # Invalid
                exit_code=0,
                passed=True,
            )

    def test_valid_validation_report_not_validated(self):
        """ValidationReport validates cleanly with overall_verdict='NOT_VALIDATED'."""
        report = ValidationReport(
            task_id="task-123",
            solution_id="sol-123",
            test_suite_id="suite-123",
            starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
            execution_mode="static",
            baseline_status="not_run",
            solution_applied_successfully=True,
            created_files=["app/cache.py"],
            modified_files=[],
            overall_verdict="NOT_VALIDATED",
            rejection_reasons=["Isolated sandbox unavailable"],
            created_at="2026-11-16T12:00:00Z",
        )
        self.assertEqual(report.overall_verdict, "NOT_VALIDATED")
        self.assertEqual(report.baseline_status, "not_run")
        self.assertEqual(report.mutation_test_status, "not_run")
        self.assertTrue(report.solution_applied_successfully)

    def test_invalid_overall_verdict_raises_error(self):
        """Verdict other than VALIDATED, REJECTED, or NOT_VALIDATED fails validation."""
        with self.assertRaises(ValidationError):
            ValidationReport(
                task_id="task-123",
                solution_id="sol-123",
                test_suite_id="suite-123",
                overall_verdict="PARTIAL_SUCCESS",  # Invalid
                created_at="2026-11-16T12:00:00Z",
            )

    def test_invalid_execution_mode_raises_error(self):
        """ExecutionMode not in Literal raises ValidationError."""
        with self.assertRaises(ValidationError):
            ValidationReport(
                task_id="task-123",
                solution_id="sol-123",
                test_suite_id="suite-123",
                execution_mode="cloud_vm",  # Invalid
                overall_verdict="NOT_VALIDATED",
                created_at="2026-11-16T12:00:00Z",
            )

    def test_validation_request_instantiation(self):
        """ValidationRequest correctly integrates TaskResponse, SolutionResponse, and TestSuiteResponse."""
        req = ValidationRequest(
            task=_make_dummy_task(),
            solution=_make_dummy_solution(),
            test_suite=_make_dummy_test_suite(),
            execution_mode="static",
            starting_commit_sha="fedcba9876543210",
        )
        self.assertEqual(req.task.id, "task-123")
        self.assertEqual(req.solution.id, "sol-123")
        self.assertEqual(req.test_suite.id, "suite-123")
        self.assertEqual(req.execution_mode, "static")
        self.assertEqual(req.starting_commit_sha, "fedcba9876543210")


if __name__ == "__main__":
    unittest.main()
