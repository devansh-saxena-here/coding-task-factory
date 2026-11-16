"""
Test Suite Schemas — Day 7 Step 1.

Defines Pydantic models for repository-aware test suites, distinguishing
new feature tests from pre-existing or synthesized regression checks,
and preserving starting repository version and framework metadata.
"""

from typing import Literal
import uuid
from pydantic import BaseModel, Field, model_validator

from app.schemas.repo import RepoAnalysisResponse
from app.schemas.solution import SolutionResponse
from app.schemas.task import TaskResponse

# ── Classification Literals ─────────────────────────────────────────

TestKind = Literal["feature", "regression"]

TestCaseType = Literal[
    "happy_path",           # Core functional/expected behavior under normal conditions
    "edge_case",            # Boundary conditions, empty sets, max values, race conditions
    "invalid_input",        # Malformed payloads, invalid types, out-of-range arguments
    "error_handling",       # Graceful degradation, connection failure, expected exceptions
    "acceptance_criterion", # Direct 1:1 mapping to a task acceptance criterion
    "regression_check",     # Verifies pre-existing functionality remains unbroken
]


# ── Test Case & File Models ──────────────────────────────────────────

class TestCase(BaseModel):
    """Represents an individual test case/assertion within a test file."""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this test case",
    )
    name: str = Field(
        ...,
        description="Function or method name of the test, e.g. 'test_cache_miss_queries_database'",
        examples=["test_cache_miss_queries_database"],
    )
    test_kind: TestKind = Field(
        ...,
        description="Whether this is a 'feature' test for new functionality or a 'regression' check",
    )
    case_type: TestCaseType = Field(
        ...,
        description="Detailed classification: happy_path, edge_case, invalid_input, error_handling, acceptance_criterion, or regression_check",
    )
    description: str = Field(
        ...,
        description="Human-readable explanation of what this test verifies and why",
    )
    target_criterion: str | None = Field(
        default=None,
        description="The specific acceptance criterion, requirement, or pre-existing behavior being verified",
    )
    expected_behavior: str = Field(
        ...,
        description="Expected assertion or outcome (e.g. 'returns 200 with cached JSON', 'raises ValueError')",
    )


class TestFile(BaseModel):
    """Represents a complete test file to be created or preserved in the repository."""
    path: str = Field(
        ...,
        description="Relative file path within the project (e.g. 'tests/test_feature_cache.py' or 'tests/test_store_regression.py')",
        examples=["tests/test_feature_cache.py"],
    )
    test_kind: TestKind = Field(
        ...,
        description="Primary role of the test file: 'feature' for new code, 'regression' for baseline safety",
    )
    framework: str = Field(
        default="pytest",
        description="Test framework used (pytest, unittest, jest, mocha, go test, etc.)",
        examples=["pytest", "unittest", "jest", "go test"],
    )
    code: str = Field(
        ...,
        description="Complete, executable-quality test code with imports, fixtures/mocks, assertions, and zero TODOs",
    )
    test_cases: list[TestCase] = Field(
        default_factory=list,
        description="Catalog of individual test cases defined within this file",
    )


# ── Repository Version & Reproducibility Metadata ───────────────────

class RepositoryMetadata(BaseModel):
    """Repository environment, starting version, and test framework metadata."""
    project_name: str = Field(
        ...,
        description="Name of the project or repository",
    )
    source_type: Literal["github", "zip", "local", "unknown"] = Field(
        default="unknown",
        description="Source from which the repository was ingested",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA representing the exact starting state of the repository",
        examples=["7fac3b2c12a84e3a4e402b8d9620b7c7b89d412e"],
    )
    detected_language: str = Field(
        default="python",
        description="Primary programming language (python, typescript, go, etc.)",
    )
    detected_frameworks: list[str] = Field(
        default_factory=list,
        description="Detected libraries or frameworks (e.g. FastAPI, Django, React, Express)",
    )
    test_framework: str = Field(
        default="pytest",
        description="Primary test framework detected from repo config or files (pytest, unittest, jest, etc.)",
    )
    test_framework_config_file: str | None = Field(
        default=None,
        description="Path to detected test configuration file (e.g. pytest.ini, pyproject.toml, package.json)",
    )
    existing_test_files: list[str] = Field(
        default_factory=list,
        description="Paths to pre-existing test files found in the repository before task generation",
    )
    environment_info: dict[str, str] = Field(
        default_factory=dict,
        description="Optional execution environment key-value pairs (e.g. {'python_version': '3.11'})",
    )


# ── Top-level Test Suite Response & Request ─────────────────────────

class TestSuiteResponse(BaseModel):
    """
    Complete repository-aware test suite package.

    Maintains a strict architectural separation between new feature tests
    and regression protection tests.
    """
    id: str = Field(
        ...,
        description="Unique UUID identifier for this test suite",
    )
    task_id: str = Field(
        ...,
        description="UUID of the task this test suite validates",
    )
    task_title: str = Field(
        ...,
        description="Title of the task",
    )
    repository: RepositoryMetadata = Field(
        ...,
        description="Starting repository version, source, and test framework metadata",
    )
    feature_test_files: list[TestFile] = Field(
        default_factory=list,
        description="Test files dedicated to verifying the newly requested feature",
    )
    regression_test_files: list[TestFile] = Field(
        default_factory=list,
        description="Test files dedicated to verifying existing repository functionality remains intact",
    )
    total_feature_tests: int = Field(
        default=0,
        ge=0,
        description="Total count of feature test cases across all feature test files",
    )
    total_regression_tests: int = Field(
        default=0,
        ge=0,
        description="Total count of regression test cases across all regression test files",
    )
    coverage_summary: str = Field(
        ...,
        description="Summary of coverage across happy paths, edge cases, invalid inputs, error handling, and regression checks",
    )
    execution_instructions: str = Field(
        ...,
        description="Concrete command line to execute the full test suite (e.g. 'pytest tests/ -v')",
    )
    generated_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when the test suite was produced",
    )


class TestSuiteRequest(BaseModel):
    """
    Request model for generating a repository-aware test suite.
    """
    task: TaskResponse = Field(
        ...,
        description="The generated coding task specification to create tests for",
    )
    solution: SolutionResponse | None = Field(
        default=None,
        description="Optional reference solution to align test assertions with canonical signatures",
    )
    repo_analysis: RepoAnalysisResponse | None = Field(
        default=None,
        description="Optional repository analysis data providing starting commit SHA and existing test files",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Explicit starting Git commit SHA override if not present in repo_analysis",
    )
    preferred_framework: str | None = Field(
        default=None,
        description="Optional override for target test framework (e.g. 'pytest', 'unittest', 'jest', 'go test')",
    )

    @model_validator(mode="after")
    def verify_solution_task_id(self) -> "TestSuiteRequest":
        """Ensures that solution task_id matches task.id if solution is provided."""
        if self.solution and self.solution.task_id != self.task.id:
            raise ValueError(
                f"Solution task_id '{self.solution.task_id}' does not match Task ID '{self.task.id}'"
            )
        return self
