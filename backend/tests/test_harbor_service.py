"""
Unit tests for harbor_service — Day 9 Step 3.

Tests package directory assembly, TOML generation, instruction rendering,
verifier script creation, reward recording, ZIP archive integrity,
path traversal security, forbidden file rejections, and cleanup guarantees.
Zero untrusted code is executed.
"""

import json
from pathlib import Path
import tempfile
import tomllib
import unittest
import zipfile

from app.schemas.harbor import (
    HarborEnvironmentConfig,
    HarborExportRequest,
    HarborMetadataConfig,
    HarborTaskInfo,
    HarborTaskManifest,
)
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestCase, TestFile, TestSuiteResponse
from app.schemas.validation import ValidationReport
from app.services import harbor_service
from app.services.harbor_service import (
    export_harbor_task_package,
    extract_harbor_reward,
    find_and_extract_harbor_reward,
    generate_environment_dockerfile,
    generate_instruction_markdown,
    generate_oracle_solve_sh,
    generate_task_toml,
    generate_verifier_dockerfile,
    generate_verifier_test_sh,
    parse_finite_numeric_reward,
    validate_export_file_path,
)


def _make_dummy_task(task_id: str = "task-exp-1234", commit_sha: str | None = "a1b2c3d4e5f67890123456789abcdef012345678") -> TaskResponse:
    return TaskResponse(
        id=task_id,
        topic="Codebase: store_api (Redis caching)",
        difficulty="medium",
        language="python",
        category="backend",
        title="Add Redis Caching to Store Items Endpoint",
        description="Our store API currently queries the DB on every lookup. Implement Redis caching.",
        requirements=[
            "Add redis to requirements.txt",
            "Create Redis client helper with 60s TTL",
        ],
        acceptance_criteria=[
            "GET /items caches responses with 60s TTL",
            "When Redis is unreachable, fallback gracefully without 500",
        ],
        generated_at="2026-11-16T12:00:00Z",
        starting_commit_sha=commit_sha,
        project_name="store_api",
        relevant_files=["app/cache.py (new)", "app/main.py"],
    )


def _make_dummy_solution(task_id: str = "task-exp-1234") -> SolutionResponse:
    return SolutionResponse(
        id="sol-exp-5678",
        task_id=task_id,
        task_title="Add Redis Caching to Store Items Endpoint",
        architecture_notes="Uses connection pooling with lazy fallback.",
        files=[
            SolutionFile(
                path="app/cache.py",
                status="create",
                language="python",
                code="class Cache:\n    def get(self): pass\n",
                explanation="Creates Cache utility.",
            ),
            SolutionFile(
                path="app/main.py",
                status="modify",
                language="python",
                code="from app.cache import Cache\n",
                explanation="Modifies main.py to use Cache.",
            ),
        ],
        testing_guide="Run pytest tests/ -v",
        verification_steps=["Call GET /items twice"],
        generated_at="2026-11-16T12:05:00Z",
    )


def _make_dummy_test_suite(task_id: str = "task-exp-1234", commit_sha: str | None = "a1b2c3d4e5f67890123456789abcdef012345678") -> TestSuiteResponse:
    return TestSuiteResponse(
        id="suite-exp-9012",
        task_id=task_id,
        task_title="Add Redis Caching to Store Items Endpoint",
        repository=RepositoryMetadata(
            project_name="store_api",
            source_type="github",
            starting_commit_sha=commit_sha,
            detected_language="python",
            test_framework="pytest",
        ),
        feature_test_files=[
            TestFile(
                path="tests/test_feature_cache.py",
                test_kind="feature",
                framework="pytest",
                code="def test_cache_hit():\n    assert True\n",
                test_cases=[
                    TestCase(
                        name="test_cache_hit",
                        test_kind="feature",
                        case_type="happy_path",
                        description="Checks cache hit",
                        target_criterion="GET /items caches responses with 60s TTL",
                        expected_behavior="Returns cached item",
                    )
                ],
            )
        ],
        regression_test_files=[
            TestFile(
                path="tests/test_regression_checkout.py",
                test_kind="regression",
                framework="pytest",
                code="def test_checkout_unaffected():\n    assert 1 + 1 == 2\n",
                test_cases=[
                    TestCase(
                        name="test_checkout_unaffected",
                        test_kind="regression",
                        case_type="regression_check",
                        description="Checks checkout endpoint",
                        target_criterion="Pre-existing checkout preserved",
                        expected_behavior="Order succeeds",
                    )
                ],
            )
        ],
        total_feature_tests=1,
        total_regression_tests=1,
        coverage_summary="Feature & regression coverage",
        execution_instructions="pytest tests/feature tests/regression -v",
        generated_at="2026-11-16T12:10:00Z",
    )


def _make_dummy_validation(task_id: str = "task-exp-1234", verdict: str = "NOT_VALIDATED", commit_sha: str | None = "a1b2c3d4e5f67890123456789abcdef012345678") -> ValidationReport:
    return ValidationReport(
        task_id=task_id,
        solution_id="sol-exp-5678",
        test_suite_id="suite-exp-9012",
        starting_commit_sha=commit_sha,
        execution_mode="static",
        baseline_status="not_run",
        solution_applied_successfully=True,
        created_files=["app/cache.py"],
        modified_files=["app/main.py"],
        overall_verdict=verdict,
        created_at="2026-11-16T12:15:00Z",
    )


class TestHarborService(unittest.TestCase):
    """Unit tests for the Harbor export engine."""

    # ── Path & File Security Tests ──────────────────────────────────

    def test_validate_export_file_path_valid(self):
        """Safe relative paths are accepted."""
        p = validate_export_file_path("app/services/cache.py")
        self.assertEqual(p, Path("app/services/cache.py"))

    def test_validate_export_file_path_rejects_absolute(self):
        """Absolute paths raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_export_file_path("/etc/passwd")
        self.assertIn("Absolute paths are forbidden", str(ctx.exception))

    def test_validate_export_file_path_rejects_traversal(self):
        """Paths with '..' raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_export_file_path("app/../../secret.txt")
        self.assertIn("Path traversal", str(ctx.exception))

    def test_validate_export_file_path_rejects_windows_backslashes(self):
        """Paths with backslashes raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_export_file_path("app\\cache.py")
        self.assertIn("Unsafe path separator", str(ctx.exception))

    def test_validate_export_file_path_rejects_forbidden_credentials(self):
        """Credential files (.env, *.key, etc.) are strictly rejected."""
        with self.assertRaises(ValueError) as ctx:
            validate_export_file_path(".env")
        self.assertIn("Forbidden credential", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            validate_export_file_path("certs/private.key")
        self.assertIn("Forbidden file extension", str(ctx2.exception))

    # ── Text Generation & Template Tests ────────────────────────────

    def test_generate_instruction_markdown_content(self):
        """instruction.md includes requirements and criteria, but zero test assertions."""
        task = _make_dummy_task()
        content = generate_instruction_markdown(task)

        self.assertIn("# Add Redis Caching to Store Items Endpoint", content)
        self.assertIn("Add redis to requirements.txt", content)
        self.assertIn("GET /items caches responses with 60s TTL", content)
        self.assertIn("`app/cache.py`", content)
        self.assertIn("`app/main.py`", content)

        # Confirm no solution or test code leaked
        self.assertNotIn("class Cache:", content)
        self.assertNotIn("assert True", content)

    def test_generate_task_toml_format(self):
        """task.toml serializes strictly according to Harbor schema 1.4 and parses as valid TOML."""
        manifest = HarborTaskManifest(
            schema_version="1.4",
            task=HarborTaskInfo(name="ctf/task-1234", version="1.0.0", description="Add caching"),
            metadata=HarborMetadataConfig(
                author_name="Coding Task Factory",
                author_email="benchmark@codingtaskfactory.local",
                difficulty="hard",
                difficulty_explanation="Task difficulty rated as hard.",
                category="backend",
                tags=["python", "fastapi"],
                starting_commit_sha="fedcba9876543210",
                project_name="store_api",
                validation_status="NOT_VALIDATED",
            ),
            environment=HarborEnvironmentConfig(memory_mb=1024),
        )
        toml_text = generate_task_toml(manifest)

        # Parse with standard library tomllib to guarantee 100% valid TOML syntax
        parsed = tomllib.loads(toml_text)
        self.assertEqual(parsed["schema_version"], "1.4")
        self.assertEqual(parsed["artifacts"], ["/workspace"])
        self.assertEqual(parsed["task"]["name"], "ctf/task-1234")
        self.assertEqual(parsed["task"]["version"], "1.0.0")
        self.assertEqual(parsed["metadata"]["author_name"], "Coding Task Factory")
        self.assertEqual(parsed["metadata"]["author_email"], "benchmark@codingtaskfactory.local")
        self.assertEqual(parsed["metadata"]["difficulty_explanation"], "Task difficulty rated as hard.")
        self.assertNotIn("difficulty", parsed["metadata"])  # Bare unsupported 'difficulty' field not emitted
        self.assertEqual(parsed["metadata"]["starting_commit_sha"], "fedcba9876543210")
        self.assertEqual(parsed["metadata"]["validation_status"], "NOT_VALIDATED")
        self.assertEqual(parsed["environment"]["memory_mb"], 1024)
        self.assertFalse(parsed["environment"]["allow_internet"])
        self.assertEqual(parsed["agent"]["timeout_sec"], 600)
        self.assertEqual(parsed["verifier"]["timeout_sec"], 180)
        self.assertEqual(parsed["verifier"]["environment_mode"], "separate")

    def test_generate_environment_dockerfile_pins_sha_and_dependencies(self):
        """environment/Dockerfile contains starting commit SHA and exact pinned dependencies."""
        task = _make_dummy_task()
        repo_meta = RepositoryMetadata(project_name="store", starting_commit_sha="a1b2c3d4e5f67890123456789abcdef012345678")
        dockerfile = generate_environment_dockerfile(task, repo_meta)

        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn('STARTING_COMMIT_SHA="a1b2c3d4e5f67890123456789abcdef012345678"', dockerfile)
        self.assertIn("WORKDIR /workspace", dockerfile)
        self.assertIn("pip install --no-cache-dir pytest==8.3.4", dockerfile)
        # Ensure no unpinned pytest invocation exists
        self.assertNotIn("pip install --no-cache-dir pytest\n", dockerfile)

    def test_generate_verifier_dockerfile_pins_dependencies_and_artifacts(self):
        """tests/Dockerfile builds isolated verifier container with pinned pytest and artifact setup."""
        test_suite = _make_dummy_test_suite()
        dockerfile = generate_verifier_dockerfile(test_suite)

        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn("pip install --no-cache-dir pytest==8.3.4", dockerfile)
        self.assertIn("mkdir -p /workspace /logs/verifier", dockerfile)
        self.assertIn("COPY . /tests/", dockerfile)
        self.assertIn("chmod +x /tests/test.sh", dockerfile)
        self.assertIn("WORKDIR /workspace", dockerfile)

    def test_generate_verifier_test_sh_reward_writing(self):
        """tests/test.sh writes 1.0 on pass and 0.0 on fail to /logs/verifier/reward.txt with mount paths."""
        test_suite = _make_dummy_test_suite()
        script = generate_verifier_test_sh(test_suite)

        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn("set -o pipefail", script)
        self.assertIn("mkdir -p /logs/verifier", script)
        self.assertIn('REWARD_FILE="/logs/verifier/reward.txt"', script)
        self.assertIn('echo "0.0" > "$REWARD_FILE"', script)
        self.assertIn("pytest /tests/feature /tests/regression -v", script)
        self.assertIn('echo "1.0" > "$REWARD_FILE"', script)

    def test_generate_oracle_solve_sh(self):
        """solution/solve.sh copies solution files to /workspace."""
        solution = _make_dummy_solution()
        script = generate_oracle_solve_sh(solution)

        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn('cp -R "$FILES_DIR"/. /workspace/', script)

    # ── Package Assembly & Export Tests ─────────────────────────────

    def test_export_harbor_task_package_success(self):
        """Full export creates expected directory layout, valid ZIP archive, and report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            task = _make_dummy_task("task-exp-1")
            solution = _make_dummy_solution("task-exp-1")
            test_suite = _make_dummy_test_suite("task-exp-1")
            val_report = _make_dummy_validation("task-exp-1", "NOT_VALIDATED")

            req = HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
                validation_report=val_report,
                task_prefix="ctf",
            )

            zip_path, report = export_harbor_task_package(req, output_dir=out_path)

            self.assertTrue(zip_path.exists())
            self.assertEqual(report.task_id, "task-exp-1")
            self.assertEqual(report.harbor_task_name, "ctf/task-exp-1")
            self.assertEqual(report.validation_status_recorded, "NOT_VALIDATED")
            self.assertGreater(report.archive_size_bytes, 0)

            # Inspect extracted ZIP archive contents
            with zipfile.ZipFile(zip_path, "r") as zf:
                namelist = zf.namelist()
                prefix = f"ctf-task-exp-1/"

                self.assertIn(f"{prefix}task.toml", namelist)
                self.assertIn(f"{prefix}instruction.md", namelist)
                self.assertIn(f"{prefix}environment/Dockerfile", namelist)
                self.assertIn(f"{prefix}tests/Dockerfile", namelist)
                self.assertIn(f"{prefix}tests/test.sh", namelist)
                self.assertIn(f"{prefix}tests/feature/test_feature_cache.py", namelist)
                self.assertIn(f"{prefix}tests/regression/test_regression_checkout.py", namelist)
                self.assertIn(f"{prefix}solution/solve.sh", namelist)
                self.assertIn(f"{prefix}solution/files/app/cache.py", namelist)
                self.assertIn(f"{prefix}solution/files/app/main.py", namelist)

    def test_export_preserves_null_sha_when_no_git_metadata(self):
        """Export gracefully handles null starting commit SHA without error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = _make_dummy_task("task-nosha", commit_sha=None)
            solution = _make_dummy_solution("task-nosha")
            test_suite = _make_dummy_test_suite("task-nosha", commit_sha=None)

            req = HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
                validation_report=None,
            )

            zip_path, report = export_harbor_task_package(req, output_dir=tmp_dir)
            self.assertTrue(zip_path.exists())

            with zipfile.ZipFile(zip_path, "r") as zf:
                toml_content = zf.read("ctf-task-nosha/task.toml").decode("utf-8")
                self.assertIn('starting_commit_sha = ""', toml_content)

    def test_export_preserves_validated_status_when_empirical_report_present(self):
        """When an actual VALIDATED report is provided, it is recorded into task.toml."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = _make_dummy_task("task-val")
            solution = _make_dummy_solution("task-val")
            test_suite = _make_dummy_test_suite("task-val")
            val_report = _make_dummy_validation("task-val", "VALIDATED")

            req = HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
                validation_report=val_report,
            )

            zip_path, report = export_harbor_task_package(req, output_dir=tmp_dir)
            self.assertEqual(report.validation_status_recorded, "VALIDATED")

            with zipfile.ZipFile(zip_path, "r") as zf:
                toml_content = zf.read("ctf-task-val/task.toml").decode("utf-8")
                self.assertIn('validation_status = "VALIDATED"', toml_content)

    def test_export_rejects_duplicate_solution_paths(self):
        """Rejects export request containing duplicate solution file paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = _make_dummy_task("task-dup")
            dup_solution = SolutionResponse(
                id="sol-dup",
                task_id="task-dup",
                task_title="Title",
                architecture_notes="Notes",
                files=[
                    SolutionFile(path="app/cache.py", status="create", language="python", code="# 1", explanation="1"),
                    SolutionFile(path="app/cache.py", status="modify", language="python", code="# 2", explanation="2"),
                ],
                testing_guide="Guide",
                verification_steps=["Step"],
                generated_at="2026-11-16T12:00:00Z",
            )
            test_suite = _make_dummy_test_suite("task-dup")

            req = HarborExportRequest(
                task=task,
                solution=dup_solution,
                test_suite=test_suite,
            )

            with self.assertRaises(ValueError) as ctx:
                export_harbor_task_package(req, output_dir=tmp_dir)
            self.assertIn("Duplicate solution file path", str(ctx.exception))

    def test_export_default_memory_is_conservative_1024mb(self):
        """Export defaults container memory to conservative 1024 MB."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = _make_dummy_task("task-mem-def")
            solution = _make_dummy_solution("task-mem-def")
            test_suite = _make_dummy_test_suite("task-mem-def")

            req = HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
            )

            zip_path, _ = export_harbor_task_package(req, output_dir=tmp_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                toml_text = zf.read("ctf-task-mem-def/task.toml").decode("utf-8")
                parsed = tomllib.loads(toml_text)
                self.assertEqual(parsed["environment"]["memory_mb"], 1024)
                self.assertEqual(parsed["artifacts"], ["/workspace"])
                self.assertEqual(parsed["task"]["version"], "1.0.0")
                self.assertEqual(parsed["metadata"]["author_name"], "Coding Task Factory")
                self.assertEqual(parsed["metadata"]["author_email"], "benchmark@codingtaskfactory.local")
                self.assertEqual(parsed["verifier"]["environment_mode"], "separate")

    def test_export_custom_memory_and_author_metadata(self):
        """Export accepts custom memory and author metadata configuration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = _make_dummy_task("task-custom")
            solution = _make_dummy_solution("task-custom")
            test_suite = _make_dummy_test_suite("task-custom")

            req = HarborExportRequest(
                task=task,
                solution=solution,
                test_suite=test_suite,
                environment=HarborEnvironmentConfig(memory_mb=2048, cpus=4.0),
                author_name="Evaluation Research Lab",
                author_email="eval@researchlab.org",
            )

            zip_path, _ = export_harbor_task_package(req, output_dir=tmp_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                toml_text = zf.read("ctf-task-custom/task.toml").decode("utf-8")
                parsed = tomllib.loads(toml_text)
                self.assertEqual(parsed["environment"]["memory_mb"], 2048)
                self.assertEqual(parsed["environment"]["cpus"], 4.0)
                self.assertEqual(parsed["metadata"]["author_name"], "Evaluation Research Lab")
                self.assertEqual(parsed["metadata"]["author_email"], "eval@researchlab.org")
                self.assertNotIn("password", toml_text)
                self.assertNotIn("api_key", toml_text)

    def test_verifier_test_sh_different_frameworks(self):
        """tests/test.sh generates proper mount paths for unittest, npm, and go test."""
        # Unittest
        suite_unittest = _make_dummy_test_suite()
        suite_unittest.repository.test_framework = "unittest"
        sh_unittest = generate_verifier_test_sh(suite_unittest)
        self.assertIn("python -m unittest discover -s /tests -v", sh_unittest)

        # NPM
        suite_npm = _make_dummy_test_suite()
        suite_npm.repository.test_framework = "jest"
        sh_npm = generate_verifier_test_sh(suite_npm)
        self.assertIn("npm test --prefix /tests", sh_npm)

        # Go test
        suite_go = _make_dummy_test_suite()
        suite_go.repository.test_framework = "go test"
        sh_go = generate_verifier_test_sh(suite_go)
        self.assertIn("go test /tests/...", sh_go)


class TestHarborRewardExtraction(unittest.TestCase):
    """Unit tests for Harbor evaluation result parsing and reward verification protocol."""

    def test_parse_finite_numeric_reward_valid(self):
        """Valid finite numeric values (int, float, numeric strings) are accepted, including 0.0."""
        self.assertEqual(parse_finite_numeric_reward(1.0), 1.0)
        self.assertEqual(parse_finite_numeric_reward(0.0), 0.0)
        self.assertEqual(parse_finite_numeric_reward(0), 0.0)
        self.assertEqual(parse_finite_numeric_reward(1), 1.0)
        self.assertEqual(parse_finite_numeric_reward("1.0"), 1.0)
        self.assertEqual(parse_finite_numeric_reward(" 0.0 "), 0.0)
        self.assertEqual(parse_finite_numeric_reward("0.85"), 0.85)

    def test_parse_finite_numeric_reward_invalid_and_rejects_bools(self):
        """None, booleans, NaN, infinities, and invalid strings are strictly rejected."""
        self.assertIsNone(parse_finite_numeric_reward(None))
        self.assertIsNone(parse_finite_numeric_reward(True))
        self.assertIsNone(parse_finite_numeric_reward(False))
        self.assertIsNone(parse_finite_numeric_reward(float("nan")))
        self.assertIsNone(parse_finite_numeric_reward(float("inf")))
        self.assertIsNone(parse_finite_numeric_reward(float("-inf")))
        self.assertIsNone(parse_finite_numeric_reward("NaN"))
        self.assertIsNone(parse_finite_numeric_reward("inf"))
        self.assertIsNone(parse_finite_numeric_reward("invalid_score"))
        self.assertIsNone(parse_finite_numeric_reward([]))
        self.assertIsNone(parse_finite_numeric_reward({}))

    def test_extract_harbor_reward_valid_trial_result(self):
        """Extracts valid reward 1.0 from TrialResult with verifier_result.rewards.reward."""
        payload = {
            "id": "trial-abc-123",
            "verifier_result": {
                "rewards": {
                    "reward": 1.0,
                },
            },
        }
        score, path = extract_harbor_reward(payload)
        self.assertEqual(score, 1.0)
        self.assertEqual(path, "verifier_result.rewards.reward")

    def test_extract_harbor_reward_valid_job_result(self):
        """Extracts valid reward 1.0 from JobResult with trial_results list."""
        payload = {
            "job_id": "job-2026-11-18",
            "trial_results": [
                {
                    "id": "trial-001",
                    "verifier_result": {
                        "rewards": {
                            "reward": 1.0,
                        },
                    },
                }
            ],
        }
        score, path = extract_harbor_reward(payload)
        self.assertEqual(score, 1.0)
        self.assertEqual(path, "trial_results[0].verifier_result.rewards.reward")

    def test_extract_harbor_reward_job_result_trials_alias(self):
        """Extracts valid reward from JobResult using trials alias."""
        payload = {
            "trials": [
                {
                    "verifier_result": {
                        "rewards": {
                            "reward": 1.0,
                        }
                    }
                }
            ]
        }
        score, path = extract_harbor_reward(payload)
        self.assertEqual(score, 1.0)
        self.assertEqual(path, "trials[0].verifier_result.rewards.reward")

    def test_extract_harbor_reward_zero_score(self):
        """Reward score 0.0 is cleanly extracted and not treated as falsy or missing."""
        payload = {
            "verifier_result": {
                "rewards": {
                    "reward": 0.0,
                },
            },
        }
        score, path = extract_harbor_reward(payload)
        self.assertEqual(score, 0.0)
        self.assertEqual(path, "verifier_result.rewards.reward")

    def test_extract_harbor_reward_single_custom_metric_key(self):
        """Extracts score from a single labeled custom metric inside rewards."""
        payload = {
            "verifier_result": {
                "rewards": {
                    "accuracy": 1.0,
                },
            },
        }
        score, path = extract_harbor_reward(payload)
        self.assertEqual(score, 1.0)
        self.assertEqual(path, "verifier_result.rewards.accuracy")

    def test_extract_harbor_reward_scalar_rewards_and_direct_reward(self):
        """Handles scalar rewards in verifier_result or direct reward property."""
        payload1 = {"verifier_result": {"rewards": 1.0}}
        score1, path1 = extract_harbor_reward(payload1)
        self.assertEqual(score1, 1.0)
        self.assertEqual(path1, "verifier_result.rewards")

        payload2 = {"verifier_result": {"reward": 1.0}}
        score2, path2 = extract_harbor_reward(payload2)
        self.assertEqual(score2, 1.0)
        self.assertEqual(path2, "verifier_result.reward")

    def test_extract_harbor_reward_missing_verifier_result(self):
        """Returns None when verifier_result is missing from trial data."""
        payload = {"id": "trial-failed-before-eval"}
        score, _ = extract_harbor_reward(payload)
        self.assertIsNone(score)

    def test_extract_harbor_reward_missing_rewards(self):
        """Returns None when rewards mapping is missing from verifier_result."""
        payload = {"verifier_result": {"metrics": {"elapsed": 12.3}}}
        score, _ = extract_harbor_reward(payload)
        self.assertIsNone(score)

    def test_extract_harbor_reward_empty_rewards_dict(self):
        """Returns None when rewards dictionary is empty."""
        payload = {"verifier_result": {"rewards": {}}}
        score, _ = extract_harbor_reward(payload)
        self.assertIsNone(score)

    def test_extract_harbor_reward_null_or_non_numeric(self):
        """Returns None when reward value is null, boolean, or non-numeric."""
        self.assertIsNone(extract_harbor_reward({"verifier_result": {"rewards": {"reward": None}}})[0])
        self.assertIsNone(extract_harbor_reward({"verifier_result": {"rewards": {"reward": "N/A"}}})[0])
        self.assertIsNone(extract_harbor_reward({"verifier_result": {"rewards": {"reward": True}}})[0])
        self.assertIsNone(extract_harbor_reward({"verifier_result": {"rewards": {"reward": float("nan")}}})[0])
        self.assertIsNone(extract_harbor_reward({"verifier_result": {"rewards": {"reward": float("inf")}}})[0])

    def test_find_and_extract_harbor_reward_from_directory(self):
        """Scans directory and extracts reward from result.json, JobResult, or reward.txt fallback."""
        with tempfile.TemporaryDirectory() as tmp_str:
            jobs_dir = Path(tmp_str)

            # 1. Non-existent jobs dir
            score, _, _ = find_and_extract_harbor_reward(jobs_dir / "nonexistent")
            self.assertIsNone(score)

            # 2. Empty jobs dir
            score, _, _ = find_and_extract_harbor_reward(jobs_dir)
            self.assertIsNone(score)

            # 3. JobResult file at job root
            job_res_file = jobs_dir / "result.json"
            job_res_file.write_text(
                json.dumps({
                    "trial_results": [
                        {
                            "verifier_result": {
                                "rewards": {
                                    "reward": 1.0,
                                },
                            },
                        }
                    ]
                }),
                encoding="utf-8",
            )
            score, src, path = find_and_extract_harbor_reward(jobs_dir)
            self.assertEqual(score, 1.0)
            self.assertIn("trial_results[0].verifier_result.rewards.reward", path)

            # 4. Deeper TrialResult file takes precedence
            trial_dir = jobs_dir / "trial_01"
            trial_dir.mkdir()
            trial_res_file = trial_dir / "result.json"
            trial_res_file.write_text(
                json.dumps({
                    "verifier_result": {
                        "rewards": {
                            "reward": 1.0,
                        },
                    },
                }),
                encoding="utf-8",
            )
            score_deep, src_deep, path_deep = find_and_extract_harbor_reward(jobs_dir)
            self.assertEqual(score_deep, 1.0)
            self.assertEqual(path_deep, "verifier_result.rewards.reward")
            self.assertIn("trial_01/result.json", src_deep)

            # 5. Fallback to reward.txt when result.json has no valid rewards
            trial_res_file.unlink()
            job_res_file.write_text(json.dumps({"status": "partial"}), encoding="utf-8")
            log_dir = trial_dir / "logs" / "verifier"
            log_dir.mkdir(parents=True)
            reward_txt = log_dir / "reward.txt"
            reward_txt.write_text("1.0\n", encoding="utf-8")

            score_txt, src_txt, path_txt = find_and_extract_harbor_reward(jobs_dir)
            self.assertEqual(score_txt, 1.0)
            self.assertEqual(path_txt, "filesystem:reward.txt")


if __name__ == "__main__":
    unittest.main()
