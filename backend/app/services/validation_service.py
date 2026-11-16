"""
Validation Service — Day 8 Step 2.

Implements safe, non-executing reference solution application, test file preparation,
path traversal security, and the abstract execution-backend interface.

Enforces zero code execution on the host machine.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os
from pathlib import Path
import time
import uuid

from app.schemas.solution import SolutionResponse
from app.schemas.test_suite import TestSuiteResponse
from app.schemas.validation import (
    BaselineStatus,
    ExecutionMode,
    MutationStatus,
    OverallVerdict,
    TestExecutionResult,
    TestRunKind,
    ValidationReport,
    ValidationRequest,
)


# ── Path Traversal & Symlink Security ───────────────────────────────

def resolve_safe_workspace_path(workspace_root: Path | str, relative_path: str) -> Path:
    """
    Safely resolves a relative path within workspace_root.

    Strictly rejects:
    - Absolute paths (e.g. /etc/passwd, C:\\Windows)
    - Path traversal components ('..' or '.')
    - Resolved paths outside workspace_root
    - Paths that traverse symlinks pointing outside workspace_root

    Raises:
        ValueError: If any traversal, absolute path, or sandbox escape is detected.
    """
    root = Path(workspace_root).resolve()
    rel = str(relative_path).strip()

    if not rel:
        raise ValueError("Relative path cannot be empty.")

    # Reject absolute indicators
    if rel.startswith("/") or rel.startswith("\\") or (len(rel) >= 2 and rel[1] == ":"):
        raise ValueError(f"Absolute paths are forbidden: '{relative_path}'")

    # Reject path traversal components in normalized path
    norm_parts = Path(rel).parts
    if any(p in ("..", ".") for p in norm_parts):
        raise ValueError(f"Path traversal ('..' or '.') is forbidden: '{relative_path}'")

    target = (root / rel).resolve()

    # Enforce strict containment
    try:
        if not target.is_relative_to(root):
            raise ValueError(f"Path escapes workspace root: '{relative_path}'")
    except AttributeError:
        # Fallback for Python versions without Path.is_relative_to
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path escapes workspace root: '{relative_path}'")

    # Check that any existing parent directory is not an external symlink
    curr = target.parent
    while curr != root and curr != curr.parent:
        if curr.is_symlink():
            resolved_link = curr.resolve()
            if not resolved_link.is_relative_to(root):
                raise ValueError(
                    f"Symlink traversal escapes workspace root: '{curr}' -> '{resolved_link}'"
                )
        curr = curr.parent

    return target


# ── Safe Reference Solution Application (Non-Executing) ─────────────

def apply_solution_safely(
    workspace_root: Path | str,
    solution: SolutionResponse,
) -> tuple[list[str], list[str]]:
    """
    Statically applies reference solution files to a controlled workspace copy.

    Enforces:
    - Path traversal prevention on every file.
    - status="modify" requires the target file to exist.
    - status="create" rejects unintended overwrites of existing files.
    - Never executes solve.sh or application code.

    Returns:
        tuple of (created_file_paths, modified_file_paths)

    Raises:
        ValueError: On path traversal, missing modify targets, or overwrite collisions.
    """
    root = Path(workspace_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Workspace root does not exist or is not a directory: {workspace_root}")

    created_paths: list[str] = []
    modified_paths: list[str] = []

    for f_idx, sol_file in enumerate(solution.files):
        target_path = resolve_safe_workspace_path(root, sol_file.path)
        rel_str = str(Path(sol_file.path)).replace("\\", "/")

        if sol_file.status == "modify":
            if not target_path.exists() or not target_path.is_file():
                raise ValueError(
                    f"Solution file #{f_idx} has status='modify' but target does not exist: '{sol_file.path}'"
                )
            target_path.write_text(sol_file.code, encoding="utf-8")
            modified_paths.append(rel_str)

        elif sol_file.status == "create":
            if target_path.exists():
                raise ValueError(
                    f"Solution file #{f_idx} has status='create' but file already exists (unintended collision): '{sol_file.path}'"
                )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(sol_file.code, encoding="utf-8")
            created_paths.append(rel_str)

    return created_paths, modified_paths


# ── Safe Test File Preparation (Non-Executing) ──────────────────────

def prepare_test_files_safely(
    workspace_root: Path | str,
    test_suite: TestSuiteResponse,
) -> tuple[list[str], list[str]]:
    """
    Statically prepares feature and regression test files in a workspace.

    Enforces:
    - Strict path containment.
    - Feature and regression tests remain distinct.
    - Does not overwrite existing repository files.
    - Rejects duplicate test file paths.
    - Never executes test code.

    Returns:
        tuple of (feature_test_paths, regression_test_paths)

    Raises:
        ValueError: On collision, traversal, or duplicate paths.
    """
    root = Path(workspace_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Workspace root does not exist or is not a directory: {workspace_root}")

    seen_paths: set[str] = set()
    feature_paths: list[str] = []
    regression_paths: list[str] = []

    # Process Feature Test Files
    for feat_file in test_suite.feature_test_files:
        rel_str = str(Path(feat_file.path)).replace("\\", "/")
        if rel_str in seen_paths:
            raise ValueError(f"Duplicate test file path in test suite: '{feat_file.path}'")

        target = resolve_safe_workspace_path(root, feat_file.path)
        if target.exists():
            raise ValueError(
                f"Feature test file collides with existing repository file: '{feat_file.path}'"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(feat_file.code, encoding="utf-8")
        seen_paths.add(rel_str)
        feature_paths.append(rel_str)

    # Process Regression Test Files
    for reg_file in test_suite.regression_test_files:
        rel_str = str(Path(reg_file.path)).replace("\\", "/")
        if rel_str in seen_paths:
            raise ValueError(f"Duplicate test file path in test suite: '{reg_file.path}'")

        target = resolve_safe_workspace_path(root, reg_file.path)
        if target.exists():
            raise ValueError(
                f"Regression test file collides with existing repository file: '{reg_file.path}'"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(reg_file.code, encoding="utf-8")
        seen_paths.add(rel_str)
        regression_paths.append(rel_str)

    return feature_paths, regression_paths


# ── Execution Backend Interface ─────────────────────────────────────

class ValidationExecutionBackend(ABC):
    """
    Abstract interface for executing tests in an isolated execution environment.
    """
    @abstractmethod
    def run_tests(
        self,
        workspace_root: Path,
        test_file: str,
        test_kind: TestRunKind,
        framework: str,
        timeout_sec: int = 30,
    ) -> TestExecutionResult:
        """Execute a test file and return bounded stdout, stderr, and exit code."""
        pass


class StaticOnlyExecutionBackend(ValidationExecutionBackend):
    """
    Default safe backend: Refuses to execute code on the host without verified isolation.
    """
    def run_tests(
        self,
        workspace_root: Path,
        test_file: str,
        test_kind: TestRunKind,
        framework: str,
        timeout_sec: int = 30,
    ) -> TestExecutionResult:
        return TestExecutionResult(
            test_file=test_file,
            test_kind=test_kind,
            exit_code=-1,
            duration_ms=0,
            stdout="",
            stderr="Host execution prohibited by security policy. Verified sandbox backend required.",
            passed=False,
        )


class HarborExecutionBackend(ValidationExecutionBackend):
    """
    Interface for Harbor / Docker sandboxed execution.
    Returns not_run when Docker/Harbor is unavailable on the host.
    """
    def run_tests(
        self,
        workspace_root: Path,
        test_file: str,
        test_kind: TestRunKind,
        framework: str,
        timeout_sec: int = 30,
    ) -> TestExecutionResult:
        return TestExecutionResult(
            test_file=test_file,
            test_kind=test_kind,
            exit_code=-1,
            duration_ms=0,
            stdout="",
            stderr="Harbor container runtime is not available on this host environment.",
            passed=False,
        )


# ── Master Validation Engine Entry Point ────────────────────────────

def validate_task_package(
    workspace_root: Path | str,
    request: ValidationRequest,
    backend: ValidationExecutionBackend | None = None,
) -> ValidationReport:
    """
    Evaluates a task package through the 5 validation gates without executing untrusted code on the host.

    Gate 1: Baseline repository tests.
    Gate 2: Solution application integrity (path security, non-collision).
    Gate 3: Feature tests.
    Gate 4: Regression tests.
    Gate 5: Mutation testing (negative control).

    In 'static' mode or when isolated execution is unavailable, returns NOT_VALIDATED.
    Never marks a task VALIDATED without empirical sandbox execution evidence.
    """
    start_time = time.monotonic()
    root = Path(workspace_root).resolve()
    rejection_reasons: list[str] = []

    commit_sha = (
        request.starting_commit_sha
        or request.task.starting_commit_sha
        or request.test_suite.repository.starting_commit_sha
    )

    execution_backend = backend or (
        HarborExecutionBackend() if request.execution_mode == "harbor" else StaticOnlyExecutionBackend()
    )

    # ── Gate 2: Solution Application Integrity ─────────────────────
    created_files: list[str] = []
    modified_files: list[str] = []
    solution_applied_ok = False

    try:
        created_files, modified_files = apply_solution_safely(root, request.solution)
        solution_applied_ok = True
    except ValueError as exc:
        rejection_reasons.append(f"Solution Application Integrity Failed: {exc}")

    # ── Prepare Test Files ─────────────────────────────────────────
    feature_paths: list[str] = []
    regression_paths: list[str] = []

    if solution_applied_ok:
        try:
            feature_paths, regression_paths = prepare_test_files_safely(root, request.test_suite)
        except ValueError as exc:
            rejection_reasons.append(f"Test File Preparation Failed: {exc}")

    # ── Gate 1, 3, 4, 5: Execution Handling ────────────────────────
    # In static mode or without container isolation, we do not execute untrusted code.
    if request.execution_mode in ("static", "trusted_local", "harbor"):
        if not solution_applied_ok:
            verdict: OverallVerdict = "REJECTED"
        else:
            verdict = "NOT_VALIDATED"
            rejection_reasons.append(
                "Verified sandbox backend unavailable: untrusted code execution on host blocked by security policy."
            )

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    return ValidationReport(
        id=str(uuid.uuid4()),
        task_id=request.task.id,
        solution_id=request.solution.id,
        test_suite_id=request.test_suite.id,
        starting_commit_sha=commit_sha,
        execution_mode=request.execution_mode,
        baseline_status="not_run",
        baseline_result=None,
        solution_applied_successfully=solution_applied_ok,
        created_files=created_files,
        modified_files=modified_files,
        feature_tests_result=None,
        regression_tests_result=None,
        mutation_test_status="not_run",
        mutation_test_result=None,
        overall_verdict=verdict,
        rejection_reasons=rejection_reasons,
        execution_duration_ms=elapsed_ms,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
