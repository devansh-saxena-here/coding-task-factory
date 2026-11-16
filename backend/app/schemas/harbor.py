"""
Harbor Schemas — Day 9 Step 2.

Implements typed Pydantic models for official Harbor-compatible task packages,
task manifests conforming to Harbor schema 1.4, environment specifications,
and export requests/reports.
"""

from typing import Literal
from pydantic import BaseModel, Field, model_validator

from app.schemas.solution import SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import TestSuiteResponse
from app.schemas.validation import ValidationReport

ValidationStatusLiteral = Literal["VALIDATED", "NOT_VALIDATED", "REJECTED"]


# ── Harbor Task TOML Sections (Schema Version 1.4) ──────────────────

class HarborTaskInfo(BaseModel):
    """Corresponds to [task] section in task.toml."""
    name: str = Field(
        ...,
        description="Unique task name conforming to Harbor conventions (e.g. 'ctf/task-1234')",
        examples=["ctf/task-1234"],
    )
    description: str = Field(
        ...,
        description="High-level task summary or prompt overview",
    )


class HarborMetadataConfig(BaseModel):
    """Corresponds to [metadata] section in task.toml."""
    difficulty: str = Field(
        default="medium",
        description="Task difficulty level (easy, medium, hard)",
    )
    category: str = Field(
        default="backend",
        description="Task engineering category (backend, frontend, fullstack, devops)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable keyword tags",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Original Git commit SHA anchoring the starting repository version",
        examples=["a1b2c3d4e5f67890123456789abcdef012345678"],
    )
    project_name: str = Field(
        default="standalone_project",
        description="Name of the underlying project or repository",
    )
    validation_status: ValidationStatusLiteral = Field(
        default="NOT_VALIDATED",
        description="Empirical validation status: VALIDATED, NOT_VALIDATED, or REJECTED",
    )


class HarborEnvironmentConfig(BaseModel):
    """Corresponds to [environment] section in task.toml."""
    cpus: float = Field(
        default=2.0,
        gt=0,
        description="CPU core allocation for the container sandbox",
    )
    memory_mb: int = Field(
        default=4096,
        gt=0,
        description="RAM allocation in megabytes (MB), e.g. 4096 for 4GB",
    )
    storage_mb: int = Field(
        default=10240,
        gt=0,
        description="Disk storage allocation in megabytes (MB), e.g. 10240 for 10GB",
    )
    allow_internet: bool = Field(
        default=False,
        description="Whether network/internet access is permitted during evaluation",
    )
    build_timeout_sec: int = Field(
        default=600,
        gt=0,
        description="Container build timeout threshold in seconds",
    )


class HarborAgentConfig(BaseModel):
    """Corresponds to [agent] section in task.toml."""
    timeout_sec: int = Field(
        default=600,
        gt=0,
        description="Maximum agent interaction timeout in seconds",
    )


class HarborVerifierConfig(BaseModel):
    """Corresponds to [verifier] section in task.toml."""
    timeout_sec: int = Field(
        default=180,
        gt=0,
        description="Maximum verifier execution timeout in seconds",
    )


class HarborTaskManifest(BaseModel):
    """
    Root manifest model strictly reflecting Harbor task.toml schema 1.4.
    """
    schema_version: str = Field(
        default="1.4",
        description="Official Harbor schema version",
    )
    task: HarborTaskInfo
    metadata: HarborMetadataConfig
    environment: HarborEnvironmentConfig = Field(default_factory=HarborEnvironmentConfig)
    agent: HarborAgentConfig = Field(default_factory=HarborAgentConfig)
    verifier: HarborVerifierConfig = Field(default_factory=HarborVerifierConfig)


# ── Harbor Export Request and Report Models ─────────────────────────

class HarborExportRequest(BaseModel):
    """
    Request payload to package a validated task into official Harbor format.
    """
    task: TaskResponse = Field(
        ...,
        description="The task specification",
    )
    solution: SolutionResponse = Field(
        ...,
        description="The reference solution",
    )
    test_suite: TestSuiteResponse = Field(
        ...,
        description="The test suite with feature and regression tests",
    )
    validation_report: ValidationReport | None = Field(
        default=None,
        description="Empirical validation report. When missing, validation_status is recorded as NOT_VALIDATED",
    )
    task_prefix: str = Field(
        default="ctf",
        description="Namespace prefix for Harbor task naming (e.g. 'ctf')",
    )

    @model_validator(mode="after")
    def verify_matching_task_ids(self) -> "HarborExportRequest":
        """Ensures that all supplied task, solution, and test artifacts refer to the exact same task ID."""
        task_id = self.task.id
        if self.solution.task_id != task_id:
            raise ValueError(
                f"Solution task_id '{self.solution.task_id}' does not match Task ID '{task_id}'"
            )
        if self.test_suite.task_id != task_id:
            raise ValueError(
                f"TestSuite task_id '{self.test_suite.task_id}' does not match Task ID '{task_id}'"
            )
        if self.validation_report:
            if self.validation_report.task_id != task_id:
                raise ValueError(
                    f"ValidationReport task_id '{self.validation_report.task_id}' does not match Task ID '{task_id}'"
                )
            if self.validation_report.solution_id != self.solution.id:
                raise ValueError(
                    f"ValidationReport solution_id '{self.validation_report.solution_id}' does not match Solution ID '{self.solution.id}'"
                )
            if self.validation_report.test_suite_id != self.test_suite.id:
                raise ValueError(
                    f"ValidationReport test_suite_id '{self.validation_report.test_suite_id}' does not match TestSuite ID '{self.test_suite.id}'"
                )
        return self

    def resolve_starting_commit_sha(self) -> str | None:
        """Determines the starting commit SHA consistently across artifacts."""
        if self.validation_report and self.validation_report.starting_commit_sha:
            return self.validation_report.starting_commit_sha
        if self.test_suite.repository.starting_commit_sha:
            return self.test_suite.repository.starting_commit_sha
        return self.task.starting_commit_sha

    def resolve_validation_status(self) -> ValidationStatusLiteral:
        """Determines the validation status strictly without fabricating empirical proof."""
        if self.validation_report:
            return self.validation_report.overall_verdict
        return "NOT_VALIDATED"


class HarborExportReport(BaseModel):
    """
    Summary report returned when a task is packaged for Harbor.
    """
    task_id: str = Field(..., description="ID of the packaged task")
    harbor_task_name: str = Field(..., description="Formatted Harbor task identifier (e.g. 'ctf/task-1234')")
    export_directory: str = Field(..., description="Staged package directory path")
    archive_path: str | None = Field(default=None, description="Path to generated ZIP archive if bundled")
    files_exported: list[str] = Field(default_factory=list, description="List of relative file paths in package")
    archive_size_bytes: int = Field(default=0, ge=0, description="Size of the export archive in bytes")
    validation_status_recorded: ValidationStatusLiteral = Field(
        ...,
        description="Validation status written into task.toml metadata",
    )
    exported_at: str = Field(..., description="ISO-8601 UTC timestamp")
