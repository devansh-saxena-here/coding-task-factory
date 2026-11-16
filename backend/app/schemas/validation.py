"""
Validation Schemas — Day 8 Step 2.

Defines structured Pydantic models for validation reports, test execution results,
execution modes, and validation requests without executing code.
"""

from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field, model_validator

from app.schemas.solution import SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import TestSuiteResponse

# ── Status and Mode Literals ────────────────────────────────────────

ExecutionMode = Literal["static", "trusted_local", "isolated", "harbor"]

OverallVerdict = Literal["VALIDATED", "REJECTED", "NOT_VALIDATED"]

BaselineStatus = Literal["passed", "failed", "not_run", "skipped"]

MutationStatus = Literal["passed", "failed", "not_run"]

TestRunKind = Literal["baseline", "feature", "regression", "mutation"]


# ── Execution Result Schema ─────────────────────────────────────────

class TestExecutionResult(BaseModel):
    """Encapsulates captured execution metrics from a test run inside an environment."""
    test_file: str = Field(
        ...,
        description="Relative path of the executed test file",
    )
    test_kind: TestRunKind = Field(
        ...,
        description="Category of the executed test (baseline, feature, regression, or mutation)",
    )
    exit_code: int = Field(
        ...,
        description="Process exit code (0 for pass, non-zero for failure, -1 for not run/error)",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Execution duration in milliseconds",
    )
    stdout: str = Field(
        default="",
        max_length=100_000,
        description="Bounded stdout captured during execution",
    )
    stderr: str = Field(
        default="",
        max_length=100_000,
        description="Bounded stderr captured during execution",
    )
    passed: bool = Field(
        ...,
        description="Whether this test run passed successfully (exit code 0 and valid assertions)",
    )
    individual_cases: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-test case outcome breakdown if parsed from test runner output",
    )


# ── Top-level Validation Report Schema ──────────────────────────────

class ValidationReport(BaseModel):
    """
    Comprehensive, auditable verification report for a task package.

    Enforces that a task is never marked VALIDATED without empirical proof
    from an isolated execution sandbox.
    """
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for this validation report",
    )
    task_id: str = Field(
        ...,
        description="UUID of the task under validation",
    )
    solution_id: str = Field(
        ...,
        description="UUID of the reference solution tested",
    )
    test_suite_id: str = Field(
        ...,
        description="UUID of the test suite evaluated",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA anchoring the starting repository snapshot",
    )
    execution_mode: ExecutionMode = Field(
        default="static",
        description="Sandbox mode used ('static', 'trusted_local', 'isolated', 'harbor')",
    )

    # ── 5 Critical Verification Gates ──────────────────────────────
    # Gate 1: Baseline tests on clean repository
    baseline_status: BaselineStatus = Field(
        default="not_run",
        description="Outcome of running pre-existing tests on unmodified repository",
    )
    baseline_result: TestExecutionResult | None = Field(
        default=None,
        description="Execution details for baseline tests",
    )

    # Gate 2: Solution application integrity
    solution_applied_successfully: bool = Field(
        default=False,
        description="Whether reference solution files applied without path traversal or collision",
    )
    created_files: list[str] = Field(
        default_factory=list,
        description="Files successfully created by reference solution",
    )
    modified_files: list[str] = Field(
        default_factory=list,
        description="Files successfully modified by reference solution",
    )

    # Gate 3: Feature tests on reference solution
    feature_tests_result: TestExecutionResult | None = Field(
        default=None,
        description="Execution result of feature tests against reference solution",
    )

    # Gate 4: Regression tests on reference solution
    regression_tests_result: TestExecutionResult | None = Field(
        default=None,
        description="Execution result of regression checks against reference solution",
    )

    # Gate 5: Mutation test / negative control
    mutation_test_status: MutationStatus = Field(
        default="not_run",
        description="Status of mutation test (passed = detected mutant, failed = missed mutant, not_run = unavailable)",
    )
    mutation_test_result: TestExecutionResult | None = Field(
        default=None,
        description="Execution details of negative control test",
    )

    # ── Verdict & Audit Trail ───────────────────────────────────────
    overall_verdict: OverallVerdict = Field(
        ...,
        description="Final evaluation verdict: VALIDATED, REJECTED, or NOT_VALIDATED",
    )
    rejection_reasons: list[str] = Field(
        default_factory=list,
        description="Detailed list of failed gates or safety violations if not validated",
    )
    execution_duration_ms: int = Field(
        default=0,
        ge=0,
        description="Total duration of the validation pipeline run in milliseconds",
    )
    created_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when the report was generated",
    )


# ── Validation Request Schema ───────────────────────────────────────

class ValidationRequest(BaseModel):
    """
    Request payload to validate a complete coding task package.
    """
    task: TaskResponse = Field(
        ...,
        description="Task specification under test",
    )
    solution: SolutionResponse = Field(
        ...,
        description="Reference solution to validate",
    )
    test_suite: TestSuiteResponse = Field(
        ...,
        description="Automated test suite to execute against solution",
    )
    execution_mode: ExecutionMode = Field(
        default="static",
        description="Execution backend to target (default: 'static' for non-executing verification)",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Explicit starting commit SHA override if not present in task",
    )

    @model_validator(mode="after")
    def verify_matching_task_ids(self) -> "ValidationRequest":
        """Ensures all artifacts in the validation request refer to the same task ID."""
        task_id = self.task.id
        if self.solution.task_id != task_id:
            raise ValueError(
                f"Solution task_id '{self.solution.task_id}' does not match Task ID '{task_id}'"
            )
        if self.test_suite.task_id != task_id:
            raise ValueError(
                f"TestSuite task_id '{self.test_suite.task_id}' does not match Task ID '{task_id}'"
            )
        return self
