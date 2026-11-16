"""
Unit tests for validation_service — Day 8 Step 2.

Tests path containment, safe solution application, test file preparation,
collision prevention, static-only execution, and NOT_VALIDATED security boundaries.
Zero untrusted code is executed.
"""

from pathlib import Path
import tempfile
import unittest

from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestCase, TestFile, TestSuiteResponse
from app.schemas.validation import ValidationRequest
from app.services import validation_service
from app.services.validation_service import (
    apply_solution_safely,
    prepare_test_files_safely,
    resolve_safe_workspace_path,
    validate_task_package,
)


def _make_dummy_task() -> TaskResponse:
    return TaskResponse(
        id="task-uuid-1",
        topic="topic",
        difficulty="medium",
        language="python",
        category="backend",
        title="Title",
        description="Desc",
        requirements=["R1"],
        acceptance_criteria=["AC1"],
        generated_at="2026-11-16T12:00:00Z",
        starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
    )


class TestValidationService(unittest.TestCase):
    """Unit tests for the validation service utilities and gates."""

    # ── Path Traversal & Security ───────────────────────────────────

    def test_resolve_safe_workspace_path_valid(self):
        """Valid relative path resolves within workspace root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir).resolve()
            resolved = resolve_safe_workspace_path(root, "app/services/cache.py")
            self.assertTrue(resolved.is_relative_to(root))
            self.assertEqual(resolved, root / "app" / "services" / "cache.py")

    def test_resolve_safe_workspace_path_rejects_absolute_posix(self):
        """Absolute POSIX path raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError) as ctx:
                resolve_safe_workspace_path(tmp_dir, "/etc/passwd")
            self.assertIn("Absolute paths are forbidden", str(ctx.exception))

    def test_resolve_safe_workspace_path_rejects_absolute_windows(self):
        """Absolute Windows drive path raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError) as ctx:
                resolve_safe_workspace_path(tmp_dir, "C:\\Windows\\System32\\calc.exe")
            self.assertIn("Absolute paths are forbidden", str(ctx.exception))

    def test_resolve_safe_workspace_path_rejects_traversal(self):
        """Path with '..' components raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError) as ctx:
                resolve_safe_workspace_path(tmp_dir, "app/../../secret.txt")
            self.assertIn("Path traversal", str(ctx.exception))

    def test_resolve_safe_workspace_path_rejects_empty(self):
        """Empty path raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                resolve_safe_workspace_path(tmp_dir, "   ")

    # ── Safe Solution Application ───────────────────────────────────

    def test_apply_solution_create_and_modify_success(self):
        """Successfully creates new files and modifies existing ones without traversal."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            # Create an existing file to modify
            existing_file = root / "app" / "main.py"
            existing_file.parent.mkdir(parents=True)
            existing_file.write_text("def old(): pass\n", encoding="utf-8")

            solution = SolutionResponse(
                id="sol-1",
                task_id="task-1",
                task_title="Title",
                architecture_notes="Notes",
                files=[
                    SolutionFile(
                        path="app/cache.py",
                        status="create",
                        language="python",
                        code="class Cache:\n    pass\n",
                        explanation="Creates cache",
                    ),
                    SolutionFile(
                        path="app/main.py",
                        status="modify",
                        language="python",
                        code="def new(): pass\n",
                        explanation="Modifies main",
                    ),
                ],
                testing_guide="Guide",
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )

            created, modified = apply_solution_safely(root, solution)
            self.assertEqual(created, ["app/cache.py"])
            self.assertEqual(modified, ["app/main.py"])
            self.assertTrue((root / "app" / "cache.py").exists())
            self.assertEqual((root / "app" / "main.py").read_text(), "def new(): pass\n")

    def test_apply_solution_modify_nonexistent_fails(self):
        """status='modify' on a file that does not exist raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            solution = SolutionResponse(
                id="sol-1",
                task_id="task-1",
                task_title="Title",
                architecture_notes="Notes",
                files=[
                    SolutionFile(
                        path="app/does_not_exist.py",
                        status="modify",
                        language="python",
                        code="# code",
                        explanation="exp",
                    )
                ],
                testing_guide="Guide",
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )
            with self.assertRaises(ValueError) as ctx:
                apply_solution_safely(root, solution)
            self.assertIn("target does not exist", str(ctx.exception))

    def test_apply_solution_create_collision_fails(self):
        """status='create' on a file that already exists raises ValueError (collision protection)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "existing.py").write_text("existing", encoding="utf-8")

            solution = SolutionResponse(
                id="sol-1",
                task_id="task-1",
                task_title="Title",
                architecture_notes="Notes",
                files=[
                    SolutionFile(
                        path="app/existing.py",
                        status="create",
                        language="python",
                        code="# code",
                        explanation="exp",
                    )
                ],
                testing_guide="Guide",
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )
            with self.assertRaises(ValueError) as ctx:
                apply_solution_safely(root, solution)
            self.assertIn("file already exists", str(ctx.exception))

    # ── Safe Test File Preparation ──────────────────────────────────

    def test_prepare_test_files_safely_success(self):
        """Successfully writes feature and regression test files without collision."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            test_suite = TestSuiteResponse(
                id="suite-1",
                task_id="task-1",
                task_title="Title",
                repository=RepositoryMetadata(project_name="repo"),
                feature_test_files=[
                    TestFile(
                        path="tests/test_feature_cache.py",
                        test_kind="feature",
                        code="def test_feat(): assert True",
                        test_cases=[],
                    )
                ],
                regression_test_files=[
                    TestFile(
                        path="tests/test_regression_order.py",
                        test_kind="regression",
                        code="def test_reg(): assert True",
                        test_cases=[],
                    )
                ],
                total_feature_tests=1,
                total_regression_tests=1,
                coverage_summary="summary",
                execution_instructions="pytest tests/ -v",
                generated_at="2026-11-16T12:00:00Z",
            )

            feat, reg = prepare_test_files_safely(root, test_suite)
            self.assertEqual(feat, ["tests/test_feature_cache.py"])
            self.assertEqual(reg, ["tests/test_regression_order.py"])
            self.assertTrue((root / "tests" / "test_feature_cache.py").exists())
            self.assertTrue((root / "tests" / "test_regression_order.py").exists())

    def test_prepare_test_files_rejects_duplicate_paths(self):
        """Rejects test suite containing duplicate test file paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            test_suite = TestSuiteResponse(
                id="suite-1",
                task_id="task-1",
                task_title="Title",
                repository=RepositoryMetadata(project_name="repo"),
                feature_test_files=[
                    TestFile(
                        path="tests/test_duplicate.py",
                        test_kind="feature",
                        code="assert True",
                        test_cases=[],
                    ),
                    TestFile(
                        path="tests/test_duplicate.py",
                        test_kind="feature",
                        code="assert True",
                        test_cases=[],
                    ),
                ],
                regression_test_files=[],
                total_feature_tests=2,
                total_regression_tests=0,
                coverage_summary="summary",
                execution_instructions="pytest tests/ -v",
                generated_at="2026-11-16T12:00:00Z",
            )
            with self.assertRaises(ValueError) as ctx:
                prepare_test_files_safely(root, test_suite)
            self.assertIn("Duplicate test file path", str(ctx.exception))

    def test_prepare_test_files_collision_with_existing_repo_file(self):
        """Rejects test file that overwrites pre-existing repository file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_existing.py").write_text("existing test")

            test_suite = TestSuiteResponse(
                id="suite-1",
                task_id="task-1",
                task_title="Title",
                repository=RepositoryMetadata(project_name="repo"),
                feature_test_files=[
                    TestFile(
                        path="tests/test_existing.py",
                        test_kind="feature",
                        code="new test",
                        test_cases=[],
                    )
                ],
                regression_test_files=[],
                total_feature_tests=1,
                total_regression_tests=0,
                coverage_summary="summary",
                execution_instructions="pytest tests/ -v",
                generated_at="2026-11-16T12:00:00Z",
            )
            with self.assertRaises(ValueError) as ctx:
                prepare_test_files_safely(root, test_suite)
            self.assertIn("collides with existing repository file", str(ctx.exception))

    # ── Static Validation & Security Boundaries ─────────────────────

    def test_validate_task_package_static_mode_returns_not_validated(self):
        """In static mode, validate_task_package returns NOT_VALIDATED without executing code."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "api.py").write_text("def run(): pass\n")

            solution = SolutionResponse(
                id="sol-1",
                task_id="task-uuid-1",
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
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )
            test_suite = TestSuiteResponse(
                id="suite-1",
                task_id="task-uuid-1",
                task_title="Title",
                repository=RepositoryMetadata(
                    project_name="repo",
                    starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678",
                ),
                feature_test_files=[
                    TestFile(
                        path="tests/test_feature.py",
                        test_kind="feature",
                        code="def test_f(): assert True",
                        test_cases=[],
                    )
                ],
                regression_test_files=[],
                total_feature_tests=1,
                total_regression_tests=0,
                coverage_summary="summary",
                execution_instructions="pytest tests/ -v",
                generated_at="2026-11-16T12:00:00Z",
            )

            req = ValidationRequest(
                task=_make_dummy_task(),
                solution=solution,
                test_suite=test_suite,
                execution_mode="static",
            )

            report = validate_task_package(root, req)
            self.assertEqual(report.overall_verdict, "NOT_VALIDATED")
            self.assertTrue(report.solution_applied_successfully)
            self.assertEqual(report.baseline_status, "not_run")
            self.assertEqual(report.mutation_test_status, "not_run")
            self.assertEqual(report.starting_commit_sha, "a1b2c3d4e5f67890123456789abcdef012345678")
            self.assertTrue(any("untrusted code execution on host blocked" in r for r in report.rejection_reasons))

    def test_validate_task_package_rejection_on_path_error(self):
        """When solution application fails, overall_verdict is REJECTED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            solution = SolutionResponse(
                id="sol-1",
                task_id="task-uuid-1",
                task_title="Title",
                architecture_notes="Notes",
                files=[
                    SolutionFile(
                        path="app/nonexistent.py",
                        status="modify",  # Fails because file doesn't exist
                        language="python",
                        code="pass",
                        explanation="exp",
                    )
                ],
                testing_guide="Guide",
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )
            test_suite = TestSuiteResponse(
                id="suite-1",
                task_id="task-uuid-1",
                task_title="Title",
                repository=RepositoryMetadata(project_name="repo"),
                feature_test_files=[],
                regression_test_files=[],
                total_feature_tests=0,
                total_regression_tests=0,
                coverage_summary="summary",
                execution_instructions="run",
                generated_at="2026-11-16T12:00:00Z",
            )
            req = ValidationRequest(
                task=_make_dummy_task(),
                solution=solution,
                test_suite=test_suite,
                execution_mode="static",
            )

            report = validate_task_package(root, req)
            self.assertEqual(report.overall_verdict, "REJECTED")
            self.assertFalse(report.solution_applied_successfully)
            self.assertTrue(any("Solution Application Integrity Failed" in r for r in report.rejection_reasons))


if __name__ == "__main__":
    unittest.main()
