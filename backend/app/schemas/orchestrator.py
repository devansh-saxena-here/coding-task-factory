"""
Orchestrator Schemas — Day 11 Step 2.

Defines Pydantic v2 schemas for the AI Coding Agent Evaluation Orchestrator:
- Agent configurations and prompt payloads
- Agent execution results and run tracking
- Multi-dimensional evaluation results and test records
- Benchmark run requests, responses, and reports

Enforces strict boundary constraints, score validation (0.0 to 1.0),
non-negative metrics, secret leakage prevention, and cross-ID consistency.
"""

from datetime import datetime, timezone
import re
from typing import Any, AsyncIterator, Literal
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Status Literals ──────────────────────────────────────────────────

AgentProviderLiteral = Literal["google", "anthropic", "openai", "custom", "mock"]
AdapterTypeLiteral = Literal["api", "cli", "mock"]

AgentExecutionStatus = Literal[
    "COMPLETED",
    "TIMEOUT",
    "FAILED",
    "CANCELLED",
    "NOT_RUN",
]

BenchmarkRunStatus = Literal[
    "PENDING",
    "PREPARING_WORKSPACE",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

ExecutionBackendLiteral = Literal[
    "mock_sandbox",
    "harbor_container",
    "remote_container",
]

FORBIDDEN_PARAMETER_KEYS: set[str] = {
    "api_key",
    "apikey",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "auth_token",
    "api_token",
    "bot_token",
    "refresh_token",
    "password",
    "private_key",
    "client_secret",
}


# ── 1. Agent Configuration Schema ────────────────────────────────────

class AgentSummary(BaseModel):
    """Safe, public overview of a registered agent adapter without sensitive details."""
    agent_id: str = Field(
        ...,
        description="Unique identifier for the agent",
        examples=["mock-replay-agent"],
    )
    display_name: str = Field(
        ...,
        description="Human-readable agent name",
        examples=["Mock Replay Agent (Simulated)"],
    )
    is_simulated: bool = Field(
        default=False,
        description="Whether this agent executes in a mock or simulated mode",
    )
    description: str | None = Field(
        default=None,
        description="Brief summary of agent capabilities",
    )


class AgentListResponse(BaseModel):
    """Response returned when listing available registered agent configurations."""
    agents: list[AgentSummary] = Field(
        default_factory=list,
        description="List of registered agent summaries",
    )


class CancelRunResponse(BaseModel):
    """Response returned upon processing a benchmark run cancellation request."""
    run_id: str = Field(
        ...,
        description="UUID of the benchmark run",
    )
    status: BenchmarkRunStatus = Field(
        ...,
        description="Updated run status post-cancellation",
    )
    message: str = Field(
        ...,
        description="Cancellation outcome explanation",
    )


class AgentConfiguration(BaseModel):

    """
    Configuration specification for a candidate AI coding agent.
    
    Strictly forbids storing raw API keys, secrets, or credentials.
    """
    agent_id: str = Field(
        ...,
        description="Unique identifier for the agent (e.g. 'gemini-flash', 'claude-code-cli')",
        examples=["gemini-flash"],
    )
    display_name: str = Field(
        ...,
        description="Human-readable name for dashboard and reports",
        examples=["Gemini 3.8 Flash (Direct API)"],
    )
    provider: AgentProviderLiteral = Field(
        ...,
        description="Agent LLM or platform provider",
    )
    model_name: str = Field(
        ...,
        description="Exact model identifier used by the provider",
        examples=["gemini-2.5-flash", "claude-3-7-sonnet"],
    )
    adapter_type: AdapterTypeLiteral = Field(
        default="api",
        description="Harness adapter archetype (api, cli, mock)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this agent is available for benchmark runs",
    )
    timeout_sec: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum execution timeout in seconds",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Safe non-secret operational parameters (e.g. temperature, max_tokens)",
    )

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        clean = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", clean):
            raise ValueError(
                f"agent_id '{v}' contains invalid characters. Use only letters, digits, hyphens, and underscores."
            )
        return clean

    @field_validator("parameters")
    @classmethod
    def validate_no_secrets_in_parameters(cls, v: dict[str, Any]) -> dict[str, Any]:
        for key in v.keys():
            k_lower = key.lower().replace("-", "_")
            if (
                k_lower in FORBIDDEN_PARAMETER_KEYS
                or k_lower.endswith("_secret")
                or k_lower.endswith("_key")
                or k_lower.startswith("secret_")
                or (k_lower.endswith("_token") and not k_lower.startswith("max_"))
            ):
                raise ValueError(
                    f"Security violation: Sensitive key '{key}' is forbidden in AgentConfiguration. "
                    "Secrets must be loaded from environment variables only."
                )
        return v


# ── 2. Agent Prompt Payload Schema ───────────────────────────────────

class AgentPromptPayload(BaseModel):
    """Input payload dispatched to an agent adapter to execute a task."""
    task_id: str = Field(
        ...,
        description="Unique UUID of the benchmark task",
    )
    task_title: str = Field(
        ...,
        description="Title of the task to solve",
    )
    instruction_markdown: str = Field(
        ...,
        description="Full markdown instructions, requirements, and constraints",
    )
    starting_commit_sha: str | None = Field(
        default=None,
        description="Original Git commit SHA anchoring the repository snapshot",
    )
    allowed_file_context: list[str] = Field(
        default_factory=list,
        description="List of relevant file paths grounded in the codebase",
    )
    timeout_sec: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Enforced timeout ceiling for the agent execution",
    )


# ── 3. Agent Execution Result Schema ─────────────────────────────────

class AgentExecutionResult(BaseModel):
    """Captures the output, generated git patch, and telemetry of an agent execution."""
    agent_id: str = Field(
        ...,
        description="Identifier of the executing agent",
    )
    model_name: str = Field(
        ...,
        description="Model name that generated the changes",
    )
    execution_status: AgentExecutionStatus = Field(
        ...,
        description="Final execution outcome (COMPLETED, TIMEOUT, FAILED, CANCELLED, NOT_RUN)",
    )
    git_patch: str = Field(
        default="",
        description="Unified diff representing changes made by the agent",
    )
    modified_files: list[str] = Field(
        default_factory=list,
        description="List of files modified or created in the workspace",
    )
    prompt_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of prompt tokens consumed",
    )
    completion_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of completion tokens generated",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Execution duration in milliseconds",
    )
    raw_logs: str = Field(
        default="",
        description="Captured standard output and error streams from the agent run",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Failure or error explanation if execution did not complete",
    )

    @model_validator(mode="after")
    def validate_execution_status_consistency(self) -> "AgentExecutionResult":
        if self.execution_status == "COMPLETED" and self.failure_reason:
            raise ValueError("failure_reason must be None when execution_status is 'COMPLETED'")
        if self.execution_status in ("FAILED", "TIMEOUT") and not self.failure_reason:
            # Auto-assign standard fallback reason if not provided
            self.failure_reason = f"Execution halted with status: {self.execution_status}"
        if self.execution_status == "NOT_RUN":
            if self.duration_ms > 0:
                raise ValueError("duration_ms must be 0 when execution_status is 'NOT_RUN'")
            if self.git_patch.strip():
                raise ValueError("git_patch must be empty when execution_status is 'NOT_RUN'")
        return self


# ── 4. Benchmark Run Request & Response ──────────────────────────────

class BenchmarkRunRequest(BaseModel):
    """Request payload to initiate a benchmark evaluation run across agents."""
    task_id: str = Field(
        ...,
        description="UUID of the task package to evaluate",
    )
    agent_config_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of agent identifiers to benchmark sequentially",
    )
    execution_backend: ExecutionBackendLiteral = Field(
        default="mock_sandbox",
        description="Execution isolation backend (mock_sandbox, harbor_container, remote_container)",
    )


class BenchmarkRunResponse(BaseModel):
    """Response returned upon accepting a benchmark run request."""
    run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for this benchmark run",
    )
    task_id: str = Field(
        ...,
        description="UUID of the task under evaluation",
    )
    status: BenchmarkRunStatus = Field(
        default="PENDING",
        description="Initial benchmark status",
    )
    agent_config_ids: list[str] = Field(
        ...,
        description="Agents queued for evaluation",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp of initiation",
    )


# ── 5. Agent Run Record Schema ───────────────────────────────────────

class AgentRun(BaseModel):
    """Execution lifecycle record for a single agent within a benchmark run."""
    agent_run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for this agent execution attempt",
    )
    benchmark_run_id: str = Field(
        ...,
        description="UUID of the parent benchmark run",
    )
    agent_id: str = Field(
        ...,
        description="Identifier of the agent configuration evaluated",
    )
    status: AgentExecutionStatus = Field(
        default="NOT_RUN",
        description="Current state of the agent evaluation",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when agent execution began",
    )
    completed_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when agent finished or halted",
    )
    execution_result: AgentExecutionResult | None = Field(
        default=None,
        description="Detailed agent telemetry and patch if executed",
    )


# ── 6. Test Execution Record Schema ──────────────────────────────────

class TestExecutionRecord(BaseModel):
    """Structured breakdown of feature and regression test passes and failures."""
    test_suite_id: str = Field(
        ...,
        description="UUID of the test suite evaluated against the agent patch",
    )
    feature_tests_total: int = Field(default=0, ge=0)
    feature_tests_passed: int = Field(default=0, ge=0)
    feature_tests_failed: int = Field(default=0, ge=0)
    regression_tests_total: int = Field(default=0, ge=0)
    regression_tests_passed: int = Field(default=0, ge=0)
    regression_tests_failed: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    error_information: str | None = Field(
        default=None,
        description="Fatal test runner exception or verifier error if any",
    )

    @model_validator(mode="after")
    def validate_test_counts(self) -> "TestExecutionRecord":
        if self.feature_tests_passed + self.feature_tests_failed > self.feature_tests_total:
            raise ValueError(
                f"Feature tests passed ({self.feature_tests_passed}) + failed ({self.feature_tests_failed}) "
                f"exceeds total ({self.feature_tests_total})"
            )
        if self.regression_tests_passed + self.regression_tests_failed > self.regression_tests_total:
            raise ValueError(
                f"Regression tests passed ({self.regression_tests_passed}) + failed ({self.regression_tests_failed}) "
                f"exceeds total ({self.regression_tests_total})"
            )
        return self


# ── 7. Multi-Dimensional Evaluation Result Schema ────────────────────

class EvaluationResult(BaseModel):
    """
    Evaluation scorecard calculated after running the verifier on an agent patch.
    
    All score ratios are strictly validated within [0.0, 1.0].
    """
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for this evaluation result",
    )
    agent_run_id: str = Field(
        ...,
        description="UUID of the associated agent run",
    )
    benchmark_run_id: str = Field(
        ...,
        description="UUID of the parent benchmark run",
    )
    agent_id: str = Field(
        ...,
        description="Identifier of the evaluated agent",
    )
    feature_pass_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proportion of acceptance criteria feature tests passed (0.0 to 1.0)",
    )
    regression_preservation_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proportion of existing repository regression checks preserved (0.0 to 1.0)",
    )
    diff_quality_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Score based on patch cleanliness and containment (0.0 to 1.0)",
    )
    composite_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weighted composite score: (0.50 * Feature) + (0.35 * Regression) + (0.15 * Quality)",
    )
    harbor_reward: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Official Harbor reward score: 1.0 if all tests pass; 0.0 otherwise",
    )
    passed_all: bool = Field(
        ...,
        description="Whether 100% of feature and regression tests succeeded without errors",
    )
    failure_diagnostics: list[str] = Field(
        default_factory=list,
        description="Actionable diagnostic messages detailing test failures",
    )
    test_record: TestExecutionRecord | None = Field(
        default=None,
        description="Underlying test counts and durations",
    )
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp of evaluation",
    )

    @field_validator("harbor_reward")
    @classmethod
    def validate_harbor_reward_binary(cls, v: float) -> float:
        if v not in (0.0, 1.0):
            raise ValueError(f"harbor_reward must be exactly 0.0 or 1.0 according to Harbor standard; received: {v}")
        return v

    @model_validator(mode="after")
    def validate_passed_all_consistency(self) -> "EvaluationResult":
        if self.passed_all and self.harbor_reward != 1.0:
            raise ValueError("When passed_all is True, harbor_reward must be 1.0")
        if not self.passed_all and self.harbor_reward == 1.0:
            raise ValueError("When passed_all is False, harbor_reward cannot be 1.0")
        return self


# ── 8. Benchmark Report Schema ───────────────────────────────────────

class BenchmarkReport(BaseModel):
    """
    Comprehensive benchmark report aggregating multi-agent evaluation results.
    """
    run_id: str = Field(
        ...,
        description="UUID of the benchmark run",
    )
    task_id: str = Field(
        ...,
        description="UUID of the evaluated coding task",
    )
    status: BenchmarkRunStatus = Field(
        ...,
        description="Overall benchmark completion status",
    )
    created_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of run creation",
    )
    completed_at: str | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp of run completion",
    )
    agent_runs: list[AgentRun] = Field(
        default_factory=list,
        description="Individual agent run lifecycle records",
    )
    evaluation_results: list[EvaluationResult] = Field(
        default_factory=list,
        description="Evaluated scorecards for each agent",
    )
    winner_agent_id: str | None = Field(
        default=None,
        description="Agent ID achieving the highest composite score (if completed)",
    )
    summary: str = Field(
        default="",
        description="Narrative overview summarizing performance across agents",
    )

    @model_validator(mode="after")
    def validate_report_relationships(self) -> "BenchmarkReport":
        # Ensure all evaluation results and runs belong to this run_id
        for ar in self.agent_runs:
            if ar.benchmark_run_id != self.run_id:
                raise ValueError(
                    f"AgentRun benchmark_run_id '{ar.benchmark_run_id}' does not match report run_id '{self.run_id}'"
                )
        for er in self.evaluation_results:
            if er.benchmark_run_id != self.run_id:
                raise ValueError(
                    f"EvaluationResult benchmark_run_id '{er.benchmark_run_id}' does not match report run_id '{self.run_id}'"
                )
        # Winner must be one of the evaluated agents
        if self.winner_agent_id:
            evaluated_ids = {ar.agent_id for ar in self.agent_runs}
            if self.winner_agent_id not in evaluated_ids:
                raise ValueError(
                    f"winner_agent_id '{self.winner_agent_id}' is not in the list of evaluated agents: {evaluated_ids}"
                )
        return self
