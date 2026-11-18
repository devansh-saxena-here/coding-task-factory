"""
Scoring Engine — Day 11 Step 3.

Pure, deterministic evaluation scoring engine for the AI Coding Agent Benchmark Orchestrator.
Calculates multi-dimensional performance scorecards based on verified test execution records,
diff containment and safety, and Harbor reward conventions.

Scoring Formula:
    Composite Score = (0.50 * F) + (0.35 * R) + (0.15 * D)

Where:
    F = Feature Pass Rate (passed / total feature tests)
    R = Regression Preservation Rate (passed / total regression tests)
    D = Diff Quality Score (1.0 = valid & contained, 0.5 = unrelated files, 0.0 = invalid/unsafe)

Zero untrusted code is executed during scoring.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Sequence
import uuid

from app.schemas.orchestrator import (
    AgentExecutionResult,
    EvaluationResult,
    TestExecutionRecord,
)

# Obvious placeholder markers indicating unfulfilled implementations
OBVIOUS_PLACEHOLDERS: tuple[str, ...] = (
    "TODO",
    "FIXME",
    "pass  # TODO",
    "raise NotImplementedError",
    "...",
)


class ScoringEngine:
    """
    Independent, deterministic scoring engine.
    
    Evaluates agent outcomes by consuming verifier-generated TestExecutionRecords,
    inspecting unified git diff containment safely, and enforcing Harbor binary rewards.
    """

    @classmethod
    def evaluate(
        cls,
        agent_run_id: str,
        benchmark_run_id: str,
        agent_id: str,
        execution_result: AgentExecutionResult | None,
        test_record: TestExecutionRecord | None,
        allowed_files: Sequence[str] | None = None,
        is_simulated: bool = False,
    ) -> EvaluationResult:
        """
        Calculates a validated EvaluationResult scorecard.
        
        Args:
            agent_run_id: UUID of the agent run.
            benchmark_run_id: UUID of the parent benchmark run.
            agent_id: Identifier of the evaluated agent.
            execution_result: Captured agent telemetry and git patch (if any).
            test_record: Verifier-produced test pass/fail record.
            allowed_files: List of expected or allowed file paths in the task context.
            is_simulated: Whether the run was executed in a mock/simulated environment.
            
        Returns:
            Fully populated, validated EvaluationResult.
        """
        diagnostics: list[str] = []

        if is_simulated:
            diagnostics.append(
                "[SIMULATED SCORE] This evaluation was generated using simulated mock data. "
                "It does not represent verified Harbor container execution."
            )

        # ── 1. Evaluate Agent Execution Status ──────────────────────
        agent_completed = False
        if not execution_result:
            diagnostics.append("Missing agent execution result: agent did not run or report data.")
        elif execution_result.execution_status == "COMPLETED":
            agent_completed = True
        else:
            diagnostics.append(
                f"Agent execution did not complete successfully (status: {execution_result.execution_status}). "
                f"Reason: {execution_result.failure_reason or 'None'}"
            )

        # ── 2. Evaluate Diff Quality (D) ─────────────────────────────
        diff_quality_score, diff_diagnostics = cls._evaluate_diff_quality(
            execution_result=execution_result,
            allowed_files=allowed_files,
        )
        diagnostics.extend(diff_diagnostics)

        # ── 3. Evaluate Verifier Test Results (F & R) ────────────────
        feature_pass_rate = 0.0
        regression_preservation_rate = 0.0
        has_valid_tests = False

        if test_record is None:
            diagnostics.append(
                "Verifier test record is missing: no feature or regression tests were executed."
            )
        elif test_record.feature_tests_total == 0 and test_record.regression_tests_total == 0:
            diagnostics.append(
                "Zero total tests recorded in test suite: pass rate cannot be established without tests."
            )
        else:
            # Feature Tests (F)
            if test_record.feature_tests_total > 0:
                feature_pass_rate = round(
                    test_record.feature_tests_passed / test_record.feature_tests_total, 4
                )
                if feature_pass_rate < 1.0:
                    diagnostics.append(
                        f"Feature test failure: {test_record.feature_tests_failed} of "
                        f"{test_record.feature_tests_total} feature checks failed."
                    )
            else:
                diagnostics.append("Zero feature tests present in test suite.")

            # Regression Tests (R)
            if test_record.regression_tests_total > 0:
                regression_preservation_rate = round(
                    test_record.regression_tests_passed / test_record.regression_tests_total, 4
                )
                if regression_preservation_rate < 1.0:
                    diagnostics.append(
                        f"Regression test regression detected: {test_record.regression_tests_failed} of "
                        f"{test_record.regression_tests_total} pre-existing checks broke."
                    )
            else:
                diagnostics.append("Zero regression checks present in test suite.")

            has_valid_tests = (test_record.feature_tests_total > 0)

        # ── 4. Calculate Composite Score & Harbor Reward ─────────────
        # If tests are missing or invalid, score is not fabricated
        if not has_valid_tests or not agent_completed:
            composite_score = 0.0
            harbor_reward = 0.0
            passed_all = False
            if not has_valid_tests:
                diagnostics.append("Composite score withheld (0.0): verifiable test evidence is required.")
        else:
            raw_composite = (
                (0.50 * feature_pass_rate)
                + (0.35 * regression_preservation_rate)
                + (0.15 * diff_quality_score)
            )
            composite_score = round(min(1.0, max(0.0, raw_composite)), 4)

            # Harbor reward: binary 1.0 if and only if all tests pass, diff is valid, and not simulated
            tests_all_passed = (
                feature_pass_rate == 1.0
                and regression_preservation_rate == 1.0
                and diff_quality_score > 0.0
                and not is_simulated
            )

            if tests_all_passed:
                harbor_reward = 1.0
                passed_all = True
                diagnostics.append("Harbor evaluation passed: All feature and regression checks satisfied.")
            else:
                harbor_reward = 0.0
                passed_all = False
                if is_simulated:
                    diagnostics.append(
                        "Harbor reward withheld (0.0): simulated execution does not qualify for verified Harbor container reward."
                    )
                else:
                    diagnostics.append("Harbor evaluation failed: One or more test suites or diff requirements failed.")

        return EvaluationResult(
            id=str(uuid.uuid4()),
            agent_run_id=agent_run_id,
            benchmark_run_id=benchmark_run_id,
            agent_id=agent_id,
            feature_pass_rate=feature_pass_rate,
            regression_preservation_rate=regression_preservation_rate,
            diff_quality_score=diff_quality_score,
            composite_score=composite_score,
            harbor_reward=harbor_reward,
            passed_all=passed_all,
            failure_diagnostics=diagnostics,
            test_record=test_record,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Safe Diff Inspection Helpers ─────────────────────────────────

    @classmethod
    def _evaluate_diff_quality(
        cls,
        execution_result: AgentExecutionResult | None,
        allowed_files: Sequence[str] | None,
    ) -> tuple[float, list[str]]:
        """
        Statically evaluates patch quality, safety, and file containment.
        
        Returns:
            tuple of (diff_quality_score, diagnostics)
        """
        diagnostics: list[str] = []

        if not execution_result or not execution_result.git_patch.strip():
            diagnostics.append("Diff inspection: Patch is empty (no changes made to codebase).")
            return 0.0, diagnostics

        patch = execution_result.git_patch

        # 1. Check for basic unified diff markers
        has_diff_headers = bool(re.search(r"^diff --git|--- |\+\+\+ ", patch, re.MULTILINE))
        if not has_diff_headers:
            diagnostics.append("Diff inspection: Patch is malformed (missing standard unified diff headers).")
            return 0.0, diagnostics

        # 2. Extract and inspect all modified file paths safely
        modified_paths = cls._extract_patch_paths(patch)
        if not modified_paths:
            diagnostics.append("Diff inspection: Could not extract target file paths from patch headers.")
            return 0.0, diagnostics

        for raw_path in modified_paths:
            is_safe, error_msg = cls._is_path_safe(raw_path)
            if not is_safe:
                diagnostics.append(f"Security rejection in diff: {error_msg} ('{raw_path}').")
                return 0.0, diagnostics

        # 3. Check for obvious placeholders in added lines
        added_lines = [
            line[1:].strip()
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        has_placeholder = any(
            any(ph in line for ph in OBVIOUS_PLACEHOLDERS)
            for line in added_lines
        )
        if has_placeholder:
            diagnostics.append("Diff inspection: Patch contains unfulfilled placeholders (TODO, FIXME, or ellipsis).")

        # 4. Containment against allowed_files list
        if allowed_files:
            normalized_allowed = {
                Path(p).as_posix().lstrip("./")
                for p in allowed_files
            }
            unrelated = [
                p for p in modified_paths
                if Path(p).as_posix().lstrip("./") not in normalized_allowed
            ]
            if unrelated:
                diagnostics.append(
                    f"Unrelated file modification: Patch modified files outside the allowed scope: {unrelated}"
                )
                return 0.5, diagnostics

        return 1.0, diagnostics

    @classmethod
    def _extract_patch_paths(cls, patch: str) -> list[str]:
        """Extracts unique relative target paths from unified diff headers."""
        paths: set[str] = set()

        for line in patch.splitlines():
            # Match: +++ b/path/to/file.py or +++ path/to/file.py
            plus_match = re.match(r"^\+\+\+\s+(?:b/)?([^\t\r\n]+)", line)
            if plus_match:
                candidate = plus_match.group(1).strip()
                if candidate != "/dev/null":
                    paths.add(candidate)

            # Match: diff --git a/path b/path
            git_match = re.match(r"^diff --git\s+a/(.*?)\s+b/(.*)$", line)
            if git_match:
                paths.add(git_match.group(2).strip())

        return sorted(list(paths))

    @classmethod
    def _is_path_safe(cls, relative_path: str) -> tuple[bool, str]:
        """Validates that a path inside a patch is strictly relative and contained."""
        rel = str(relative_path).strip()
        if not rel:
            return False, "Empty path"

        # Reject absolute paths (POSIX leading slash or Windows drive letters)
        if rel.startswith("/") or rel.startswith("\\") or (len(rel) >= 2 and rel[1] == ":"):
            return False, "Absolute paths are forbidden in patch headers"

        # Reject path traversal
        parts = Path(rel).parts
        if any(p in ("..", ".") for p in parts):
            return False, "Path traversal ('..' or '.') is forbidden in patch headers"

        return True, ""
