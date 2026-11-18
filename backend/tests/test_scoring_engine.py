"""
Unit tests for ScoringEngine — Day 11 Step 3.
"""

import unittest

from app.orchestrator.scoring_engine import ScoringEngine
from app.schemas.orchestrator import (
    AgentExecutionResult,
    TestExecutionRecord,
)


class TestScoringEngine(unittest.TestCase):
    """Tests for pure deterministic scoring calculation and safety guardrails."""

    def setUp(self):
        self.clean_patch = (
            "diff --git a/app/core/cache.py b/app/core/cache.py\n"
            "--- a/app/core/cache.py\n"
            "+++ b/app/core/cache.py\n"
            "@@ -1,3 +1,6 @@\n"
            "+def get_cache():\n"
            "+    return True\n"
        )
        self.valid_execution = AgentExecutionResult(
            agent_id="test-agent",
            model_name="test-model",
            execution_status="COMPLETED",
            git_patch=self.clean_patch,
            modified_files=["app/core/cache.py"],
            duration_ms=1000,
        )
        self.allowed_files = ["app/core/cache.py"]

    def test_full_pass_evaluation(self):
        """100% feature and regression passes yield 1.0 composite and 1.0 Harbor reward."""
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=4,
            feature_tests_failed=0,
            regression_tests_total=6,
            regression_tests_passed=6,
            regression_tests_failed=0,
            duration_ms=800,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=self.valid_execution,
            test_record=test_record,
            allowed_files=self.allowed_files,
            is_simulated=False,
        )

        self.assertEqual(res.feature_pass_rate, 1.0)
        self.assertEqual(res.regression_preservation_rate, 1.0)
        self.assertEqual(res.diff_quality_score, 1.0)
        self.assertEqual(res.composite_score, 1.0)
        self.assertEqual(res.harbor_reward, 1.0)
        self.assertTrue(res.passed_all)

    def test_feature_failure_penalty(self):
        """Feature test failures reduce F and deny Harbor reward."""
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=2,  # 50%
            feature_tests_failed=2,
            regression_tests_total=10,
            regression_tests_passed=10,
            regression_tests_failed=0,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=self.valid_execution,
            test_record=test_record,
            allowed_files=self.allowed_files,
        )

        # F = 0.50, R = 1.0, D = 1.0
        # Composite = (0.50 * 0.5) + (0.35 * 1.0) + (0.15 * 1.0) = 0.25 + 0.35 + 0.15 = 0.75
        self.assertEqual(res.feature_pass_rate, 0.5)
        self.assertEqual(res.regression_preservation_rate, 1.0)
        self.assertEqual(res.composite_score, 0.75)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)
        self.assertTrue(any("Feature test failure" in d for d in res.failure_diagnostics))

    def test_regression_failure_penalty(self):
        """Regression test failures penalize score and deny Harbor reward."""
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=4,
            feature_tests_failed=0,
            regression_tests_total=10,
            regression_tests_passed=7,  # 70%
            regression_tests_failed=3,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=self.valid_execution,
            test_record=test_record,
            allowed_files=self.allowed_files,
        )

        # F = 1.0, R = 0.70, D = 1.0
        # Composite = (0.50 * 1.0) + (0.35 * 0.70) + (0.15 * 1.0) = 0.50 + 0.245 + 0.15 = 0.895
        self.assertEqual(res.feature_pass_rate, 1.0)
        self.assertEqual(res.regression_preservation_rate, 0.7)
        self.assertEqual(res.composite_score, 0.895)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)

    def test_missing_test_record_withholds_score(self):
        """Missing test record results in 0.0 composite and 0.0 reward, not fabricated success."""
        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=self.valid_execution,
            test_record=None,  # Missing
            allowed_files=self.allowed_files,
        )

        self.assertEqual(res.composite_score, 0.0)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)
        self.assertTrue(any("test record is missing" in d for d in res.failure_diagnostics))

    def test_zero_total_tests_withholds_score(self):
        """Zero total tests in suite must not fabricate a 100% pass score."""
        test_record = TestExecutionRecord(
            test_suite_id="ts-empty",
            feature_tests_total=0,
            feature_tests_passed=0,
            feature_tests_failed=0,
            regression_tests_total=0,
            regression_tests_passed=0,
            regression_tests_failed=0,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=self.valid_execution,
            test_record=test_record,
            allowed_files=self.allowed_files,
        )

        self.assertEqual(res.composite_score, 0.0)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)
        self.assertTrue(any("Zero total tests recorded" in d for d in res.failure_diagnostics))

    def test_failed_agent_execution_withholds_reward(self):
        """Failed or timed-out agent execution withholds reward regardless of test claims."""
        failed_execution = AgentExecutionResult(
            agent_id="test-agent",
            model_name="test-model",
            execution_status="FAILED",
            git_patch=self.clean_patch,
            failure_reason="Syntax error in generation",
        )
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=5,
            feature_tests_passed=5,
            feature_tests_failed=0,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=failed_execution,
            test_record=test_record,
        )

        self.assertEqual(res.composite_score, 0.0)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)
        self.assertTrue(any("FAILED" in d for d in res.failure_diagnostics))

    def test_timeout_agent_execution_withholds_reward(self):
        """Timed-out agent execution cannot pass."""
        timeout_execution = AgentExecutionResult(
            agent_id="test-agent",
            model_name="test-model",
            execution_status="TIMEOUT",
            failure_reason="Timeout reached",
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="test-agent",
            execution_result=timeout_execution,
            test_record=None,
        )

        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)

    def test_unsafe_path_traversal_in_patch_rejected(self):
        """Path traversal in patch sets diff quality to 0.0 and emits security diagnostic."""
        unsafe_patch = (
            "diff --git a/../../etc/passwd b/../../etc/passwd\n"
            "--- a/../../etc/passwd\n"
            "+++ b/../../etc/passwd\n"
            "@@ -1,1 +1,2 @@\n"
            "+root:pwned\n"
        )
        unsafe_execution = AgentExecutionResult(
            agent_id="attacker-agent",
            model_name="attacker-model",
            execution_status="COMPLETED",
            git_patch=unsafe_patch,
            modified_files=["../../etc/passwd"],
        )
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=2,
            feature_tests_passed=2,
            regression_tests_total=2,
            regression_tests_passed=2,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="attacker-agent",
            execution_result=unsafe_execution,
            test_record=test_record,
            allowed_files=self.allowed_files,
        )

        self.assertEqual(res.diff_quality_score, 0.0)
        self.assertEqual(res.harbor_reward, 0.0)
        self.assertFalse(res.passed_all)
        self.assertTrue(any("Security rejection in diff" in d for d in res.failure_diagnostics))

    def test_absolute_path_in_patch_rejected(self):
        """Absolute path in patch headers sets diff quality to 0.0."""
        abs_patch = (
            "diff --git a/C:/Windows/win.ini b/C:/Windows/win.ini\n"
            "--- a/C:/Windows/win.ini\n"
            "+++ b/C:/Windows/win.ini\n"
            "@@ -1,1 +1,2 @@\n"
            "+corrupt=1\n"
        )
        abs_execution = AgentExecutionResult(
            agent_id="agent-abs",
            model_name="agent-model",
            execution_status="COMPLETED",
            git_patch=abs_patch,
        )
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=2,
            feature_tests_passed=2,
            regression_tests_total=2,
            regression_tests_passed=2,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="agent-abs",
            execution_result=abs_execution,
            test_record=test_record,
        )

        self.assertEqual(res.diff_quality_score, 0.0)
        self.assertEqual(res.harbor_reward, 0.0)

    def test_unrelated_file_modification_penalty(self):
        """Modifying files outside allowed_files applies 0.5 diff quality penalty."""
        unrelated_patch = (
            "diff --git a/app/unrelated.py b/app/unrelated.py\n"
            "--- a/app/unrelated.py\n"
            "+++ b/app/unrelated.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+def unrelated(): pass\n"
        )
        unrelated_execution = AgentExecutionResult(
            agent_id="agent-spill",
            model_name="model",
            execution_status="COMPLETED",
            git_patch=unrelated_patch,
            modified_files=["app/unrelated.py"],
        )
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=4,
            feature_tests_passed=4,
            regression_tests_total=4,
            regression_tests_passed=4,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="agent-spill",
            execution_result=unrelated_execution,
            test_record=test_record,
            allowed_files=["app/core/cache.py"],  # unrelated.py not here
        )

        self.assertEqual(res.diff_quality_score, 0.5)
        # F = 1.0, R = 1.0, D = 0.5 -> Composite = 0.5 + 0.35 + (0.15 * 0.5) = 0.85 + 0.075 = 0.925
        self.assertEqual(res.composite_score, 0.925)
        self.assertEqual(res.harbor_reward, 1.0)  # tests passed, diff was valid
        self.assertTrue(res.passed_all)
        self.assertTrue(any("outside the allowed scope" in d for d in res.failure_diagnostics))

    def test_simulated_flag_recorded_in_diagnostics(self):
        """When is_simulated is True, explicit diagnostic informs that evaluation was simulated."""
        test_record = TestExecutionRecord(
            test_suite_id="ts-01",
            feature_tests_total=1,
            feature_tests_passed=1,
            regression_tests_total=1,
            regression_tests_passed=1,
        )

        res = ScoringEngine.evaluate(
            agent_run_id="ar-01",
            benchmark_run_id="br-01",
            agent_id="mock-agent",
            execution_result=self.valid_execution,
            test_record=test_record,
            is_simulated=True,
        )

        self.assertTrue(any("[SIMULATED SCORE]" in d for d in res.failure_diagnostics))


if __name__ == "__main__":
    unittest.main()
