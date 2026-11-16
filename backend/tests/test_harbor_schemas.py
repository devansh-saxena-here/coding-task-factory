"""
Unit tests for Harbor Schemas — Day 9 Step 2.

Tests validation of HarborTaskManifest, HarborEnvironmentConfig,
HarborAgentConfig, HarborVerifierConfig, HarborExportRequest,
and ID consistency validation.
"""

import unittest
from pydantic import ValidationError

from app.schemas.harbor import (
    HarborAgentConfig,
    HarborEnvironmentConfig,
    HarborExportReport,
    HarborExportRequest,
    HarborMetadataConfig,
    HarborTaskInfo,
    HarborTaskManifest,
    HarborVerifierConfig,
)
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestCase, TestFile, TestSuiteResponse
from app.schemas.validation import ValidationReport


def _make_dummy_task(task_id: str = "task-uuid-1234") -> TaskResponse:
    return TaskResponse(
        id=task_id,
        topic="topic",
        difficulty="medium",
        language="python",
        category="backend",
        title="Implement Caching Layer",
        description="Task description",
        requirements=["Requirement 1"],
        acceptance_criteria=["Criterion 1"],
        generated_at="2026-11-16T12:00:00Z",
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
        project_name="store_api",
    )


def _make_dummy_solution(task_id: str = "task-uuid-1234") -> SolutionResponse:
    return SolutionResponse(
        id="sol-uuid-5678",
        task_id=task_id,
        task_title="Implement Caching Layer",
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


def _make_dummy_test_suite(task_id: str = "task-uuid-1234") -> TestSuiteResponse:
    return TestSuiteResponse(
        id="suite-uuid-9012",
        task_id=task_id,
        task_title="Implement Caching Layer",
        repository=RepositoryMetadata(
            project_name="store_api",
            starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
        ),
        feature_test_files=[
            TestFile(
                path="tests/test_cache.py",
                test_kind="feature",
                code="def test_c(): assert True",
                test_cases=[
                    TestCase(
                        name="test_c",
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


def _make_dummy_validation_report(task_id: str = "task-uuid-1234", verdict: str = "NOT_VALIDATED") -> ValidationReport:
    return ValidationReport(
        task_id=task_id,
        solution_id="sol-uuid-5678",
        test_suite_id="suite-uuid-9012",
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
        execution_mode="static",
        baseline_status="not_run",
        solution_applied_successfully=True,
        created_files=["app/cache.py"],
        modified_files=[],
        overall_verdict=verdict,
        created_at="2026-11-16T12:00:00Z",
    )


class TestHarborSchemas(unittest.TestCase):
    """Unit tests for official Harbor Pydantic schemas."""

    def test_valid_harbor_task_manifest(self):
        """HarborTaskManifest validates cleanly with official schema 1.4 sections."""
        manifest = HarborTaskManifest(
            schema_version="1.4",
            task=HarborTaskInfo(
                name="ctf/task-1234",
                description="Add Redis Caching",
            ),
            metadata=HarborMetadataConfig(
                difficulty="medium",
                category="backend",
                tags=["python", "caching"],
                starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
                project_name="store_api",
                validation_status="NOT_VALIDATED",
            ),
            environment=HarborEnvironmentConfig(
                cpus=2.0,
                memory_mb=4096,
                storage_mb=10240,
                allow_internet=False,
                build_timeout_sec=600,
            ),
            agent=HarborAgentConfig(timeout_sec=600),
            verifier=HarborVerifierConfig(timeout_sec=180),
        )

        self.assertEqual(manifest.schema_version, "1.4")
        self.assertEqual(manifest.task.name, "ctf/task-1234")
        self.assertEqual(manifest.metadata.validation_status, "NOT_VALIDATED")
        self.assertEqual(manifest.environment.memory_mb, 4096)
        self.assertFalse(manifest.environment.allow_internet)
        self.assertEqual(manifest.agent.timeout_sec, 600)
        self.assertEqual(manifest.verifier.timeout_sec, 180)

    def test_invalid_resource_limits_raise_validation_error(self):
        """Invalid or non-positive resource limits raise ValidationError."""
        # cpus <= 0
        with self.assertRaises(ValidationError):
            HarborEnvironmentConfig(cpus=0.0)

        # negative memory_mb
        with self.assertRaises(ValidationError):
            HarborEnvironmentConfig(memory_mb=-512)

        # negative storage_mb
        with self.assertRaises(ValidationError):
            HarborEnvironmentConfig(storage_mb=-100)

        # negative agent timeout_sec
        with self.assertRaises(ValidationError):
            HarborAgentConfig(timeout_sec=-10)

        # negative verifier timeout_sec
        with self.assertRaises(ValidationError):
            HarborVerifierConfig(timeout_sec=0)

    def test_metadata_structure_and_defaults(self):
        """HarborMetadataConfig provides sensible defaults and validates fields."""
        meta = HarborMetadataConfig()
        self.assertEqual(meta.difficulty, "medium")
        self.assertEqual(meta.category, "backend")
        self.assertEqual(meta.tags, [])
        self.assertIsNone(meta.starting_commit_sha)
        self.assertEqual(meta.validation_status, "NOT_VALIDATED")

    def test_validation_status_literal_restriction(self):
        """validation_status must strictly be VALIDATED, NOT_VALIDATED, or REJECTED."""
        with self.assertRaises(ValidationError):
            HarborMetadataConfig(validation_status="PARTIAL")  # Invalid

        valid_statuses = ["VALIDATED", "NOT_VALIDATED", "REJECTED"]
        for status in valid_statuses:
            m = HarborMetadataConfig(validation_status=status)
            self.assertEqual(m.validation_status, status)

    def test_harbor_export_request_matching_ids(self):
        """HarborExportRequest succeeds when task, solution, and test suite share task_id."""
        task = _make_dummy_task("task-1")
        solution = _make_dummy_solution("task-1")
        test_suite = _make_dummy_test_suite("task-1")
        val_report = _make_dummy_validation_report("task-1", "NOT_VALIDATED")

        req = HarborExportRequest(
            task=task,
            solution=solution,
            test_suite=test_suite,
            validation_report=val_report,
            task_prefix="ctf",
        )
        self.assertEqual(req.task.id, "task-1")
        self.assertEqual(req.resolve_starting_commit_sha(), "a1b2c3d4e5f67890123456789abcdef012345678")
        self.assertEqual(req.resolve_validation_status(), "NOT_VALIDATED")

    def test_harbor_export_request_mismatched_solution_id_raises_error(self):
        """HarborExportRequest rejects mismatched solution task_id."""
        task = _make_dummy_task("task-1")
        solution = _make_dummy_solution("task-DIFFERENT")
        test_suite = _make_dummy_test_suite("task-1")

        with self.assertRaises(ValidationError) as ctx:
            HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
            )
        self.assertIn("does not match Task ID", str(ctx.exception))

    def test_harbor_export_request_mismatched_test_suite_id_raises_error(self):
        """HarborExportRequest rejects mismatched test_suite task_id."""
        task = _make_dummy_task("task-1")
        solution = _make_dummy_solution("task-1")
        test_suite = _make_dummy_test_suite("task-WRONG")

        with self.assertRaises(ValidationError) as ctx:
            HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
            )
        self.assertIn("does not match Task ID", str(ctx.exception))

    def test_harbor_export_request_missing_validation_report_defaults_to_not_validated(self):
        """Missing validation_report defaults validation status to NOT_VALIDATED without error."""
        task = _make_dummy_task("task-1")
        solution = _make_dummy_solution("task-1")
        test_suite = _make_dummy_test_suite("task-1")

        req = HarborExportRequest(
            task=task,
            solution=solution,
            test_suite=test_suite,
            validation_report=None,
        )
        self.assertIsNone(req.validation_report)
        self.assertEqual(req.resolve_validation_status(), "NOT_VALIDATED")

    def test_harbor_export_report_instantiation(self):
        """HarborExportReport validates cleanly."""
        report = HarborExportReport(
            task_id="task-1",
            harbor_task_name="ctf/task-1",
            export_directory="/tmp/ctf_task_1",
            archive_path="/tmp/ctf_task_1.zip",
            files_exported=["task.toml", "instruction.md", "environment/Dockerfile", "tests/test.sh", "solution/solve.sh"],
            archive_size_bytes=4096,
            validation_status_recorded="NOT_VALIDATED",
            exported_at="2026-11-16T12:00:00Z",
        )
        self.assertEqual(report.harbor_task_name, "ctf/task-1")
        self.assertEqual(report.validation_status_recorded, "NOT_VALIDATED")
        self.assertEqual(len(report.files_exported), 5)


if __name__ == "__main__":
    unittest.main()
