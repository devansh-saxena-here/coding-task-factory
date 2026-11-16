"""
Integration tests for POST /tasks/export/harbor endpoint — Day 9 Step 4.

Verifies end-to-end Harbor task export API behavior:
- ZIP archive generation and downloadable Content-Disposition response.
- Complete Harbor schema 1.4 layout inside the ZIP archive.
- Verification that instruction.md does not leak reference code.
- Verifier reward protocol in tests/test.sh.
- Solution oracle script in solution/solve.sh.
- Cross-artifact ID consistency validation (422 Unprocessable Entity).
- Proper recording of VALIDATED vs NOT_VALIDATED status.
- Graceful handling of null commit SHAs and custom task prefixes.
- Rejection of path traversal, forbidden credential files (.env), and duplicates (400 Bad Request).
- Safe 500 error handling without internal path leakage.
- Backward compatibility with existing endpoints.

Zero untrusted code is executed on the host.
"""

import io
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ── Reusable Mock Data ──────────────────────────────────────────────

SAMPLE_TASK = {
    "id": "task-harbor-1234",
    "topic": "Codebase: store_api (Redis caching)",
    "difficulty": "medium",
    "language": "python",
    "category": "backend",
    "title": "Implement Redis Caching Layer for Store Endpoint",
    "description": "Add a Redis cache with 60s TTL to /items endpoint.",
    "requirements": ["Use redis-py connection pool", "Implement fallback on cache miss"],
    "acceptance_criteria": ["GET /items returns cached responses on second call"],
    "generated_at": "2026-11-16T12:00:00+00:00",
    "project_name": "store_api",
    "relevant_files": ["app/cache.py (new)", "app/main.py"],
    "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
}

SAMPLE_SOLUTION = {
    "id": "sol-harbor-5678",
    "task_id": "task-harbor-1234",
    "task_title": "Implement Redis Caching Layer for Store Endpoint",
    "architecture_notes": "Implemented Redis caching with connection pool.",
    "files": [
        {
            "path": "app/cache.py",
            "status": "create",
            "language": "python",
            "code": "class Cache:\n    def get(self, key):\n        return None\n",
            "explanation": "Creates Redis cache utility.",
        },
        {
            "path": "app/main.py",
            "status": "modify",
            "language": "python",
            "code": "from app.cache import Cache\n# updated main\n",
            "explanation": "Connects cache to main.",
        },
    ],
    "testing_guide": "Run pytest tests/test_cache.py",
    "verification_steps": ["Call GET /items twice to verify cache hit"],
    "generated_at": "2026-11-16T12:05:00+00:00",
}

SAMPLE_TEST_SUITE = {
    "id": "suite-harbor-9012",
    "task_id": "task-harbor-1234",
    "task_title": "Implement Redis Caching Layer for Store Endpoint",
    "repository": {
        "project_name": "store_api",
        "source_type": "github",
        "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
        "detected_language": "python",
        "test_framework": "pytest",
    },
    "feature_test_files": [
        {
            "path": "tests/test_feature_cache.py",
            "test_kind": "feature",
            "framework": "pytest",
            "code": "def test_cache_hit():\n    assert True\n",
            "test_cases": [
                {
                    "name": "test_cache_hit",
                    "test_kind": "feature",
                    "case_type": "happy_path",
                    "description": "Checks cache hit behavior",
                    "target_criterion": "GET /items returns cached responses",
                    "expected_behavior": "Returns 200",
                }
            ],
        }
    ],
    "regression_test_files": [
        {
            "path": "tests/test_regression_store.py",
            "test_kind": "regression",
            "framework": "pytest",
            "code": "def test_existing_store():\n    assert 1 + 1 == 2\n",
            "test_cases": [
                {
                    "name": "test_existing_store",
                    "test_kind": "regression",
                    "case_type": "regression_check",
                    "description": "Checks pre-existing items endpoint",
                    "target_criterion": "Pre-existing items logic intact",
                    "expected_behavior": "Returns 200",
                }
            ],
        }
    ],
    "total_feature_tests": 1,
    "total_regression_tests": 1,
    "coverage_summary": "1 feature test, 1 regression check",
    "execution_instructions": "pytest tests/feature tests/regression -v",
    "generated_at": "2026-11-16T12:10:00+00:00",
}

SAMPLE_VALIDATION_REPORT = {
    "id": "val-harbor-3456",
    "task_id": "task-harbor-1234",
    "solution_id": "sol-harbor-5678",
    "test_suite_id": "suite-harbor-9012",
    "starting_commit_sha": "a1b2c3d4e5f67890123456789abcdef012345678",
    "execution_mode": "static",
    "baseline_status": "not_run",
    "solution_applied_successfully": True,
    "created_files": ["app/cache.py"],
    "modified_files": ["app/main.py"],
    "feature_test_results": [],
    "regression_test_results": [],
    "negative_test_detected_error": False,
    "overall_verdict": "NOT_VALIDATED",
    "rejection_reason": "No isolated execution environment available.",
    "execution_time_sec": 0.05,
    "created_at": "2026-11-16T12:15:00+00:00",
}


class TestHarborEndpoint(unittest.TestCase):
    """Integration tests for POST /tasks/export/harbor."""

    def test_export_harbor_endpoint_success(self):
        """Valid export request returns 200, application/zip, and full Harbor 1.4 package."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "validation_report": SAMPLE_VALIDATION_REPORT,
            "task_prefix": "ctf",
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/zip")
        self.assertIn("attachment; filename=", resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.headers.get("x-harbor-task-name"), "ctf/task-harbor-1234")
        self.assertEqual(resp.headers.get("x-validation-status"), "NOT_VALIDATED")

        # Inspect ZIP archive contents
        zf = zipfile.ZipFile(io.BytesIO(resp.content), "r")
        namelist = zf.namelist()
        prefix = "ctf-task-harbor-1234/"

        # 1. Harbor Schema 1.4 task.toml
        self.assertIn(f"{prefix}task.toml", namelist)
        task_toml = zf.read(f"{prefix}task.toml").decode("utf-8")
        self.assertIn('schema_version = "1.4"', task_toml)
        self.assertIn('name = "ctf/task-harbor-1234"', task_toml)
        self.assertIn('validation_status = "NOT_VALIDATED"', task_toml)
        self.assertIn('starting_commit_sha = "a1b2c3d4e5f67890123456789abcdef012345678"', task_toml)
        self.assertIn("[environment]", task_toml)
        self.assertIn("[agent]", task_toml)
        self.assertIn("[verifier]", task_toml)

        # 2. instruction.md
        self.assertIn(f"{prefix}instruction.md", namelist)
        instruction_md = zf.read(f"{prefix}instruction.md").decode("utf-8")
        self.assertIn("# Implement Redis Caching Layer for Store Endpoint", instruction_md)
        self.assertIn("## Functional Requirements", instruction_md)
        self.assertIn("## Acceptance Criteria", instruction_md)
        # Verify no reference solution code is leaked
        self.assertNotIn("class Cache:", instruction_md)

        # 3. environment/Dockerfile
        self.assertIn(f"{prefix}environment/Dockerfile", namelist)
        dockerfile = zf.read(f"{prefix}environment/Dockerfile").decode("utf-8")
        self.assertIn('STARTING_COMMIT_SHA="a1b2c3d4e5f67890123456789abcdef012345678"', dockerfile)
        self.assertIn("WORKDIR /workspace", dockerfile)

        # 4. tests/ directory and reward protocol
        self.assertIn(f"{prefix}tests/test.sh", namelist)
        test_sh = zf.read(f"{prefix}tests/test.sh").decode("utf-8")
        self.assertIn('REWARD_FILE="/logs/verifier/reward.txt"', test_sh)
        self.assertIn('echo "1.0" > "$REWARD_FILE"', test_sh)
        self.assertIn('echo "0.0" > "$REWARD_FILE"', test_sh)
        self.assertIn(f"{prefix}tests/feature/test_feature_cache.py", namelist)
        self.assertIn(f"{prefix}tests/regression/test_regression_store.py", namelist)

        # 5. solution/ directory and oracle script
        self.assertIn(f"{prefix}solution/solve.sh", namelist)
        solve_sh = zf.read(f"{prefix}solution/solve.sh").decode("utf-8")
        self.assertIn('cp -R "$FILES_DIR"/. /workspace/', solve_sh)
        self.assertIn(f"{prefix}solution/files/app/cache.py", namelist)
        self.assertIn(f"{prefix}solution/files/app/main.py", namelist)

    def test_export_harbor_endpoint_mismatched_solution_id_returns_422(self):
        """Mismatched solution task_id triggers Pydantic schema validation error (422)."""
        bad_solution = dict(SAMPLE_SOLUTION)
        bad_solution["task_id"] = "task-DIFFERENT-ID"

        payload = {
            "task": SAMPLE_TASK,
            "solution": bad_solution,
            "test_suite": SAMPLE_TEST_SUITE,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("does not match Task ID", resp.text)

    def test_export_harbor_endpoint_mismatched_test_suite_id_returns_422(self):
        """Mismatched test suite task_id triggers 422 validation error."""
        bad_test_suite = dict(SAMPLE_TEST_SUITE)
        bad_test_suite["task_id"] = "task-DIFFERENT-ID"

        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": bad_test_suite,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("does not match Task ID", resp.text)

    def test_export_harbor_endpoint_mismatched_validation_report_id_returns_422(self):
        """Mismatched validation report task_id triggers 422 error."""
        bad_report = dict(SAMPLE_VALIDATION_REPORT)
        bad_report["task_id"] = "task-DIFFERENT-ID"

        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "validation_report": bad_report,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("does not match Task ID", resp.text)

    def test_export_harbor_endpoint_missing_validation_report_defaults_not_validated(self):
        """Missing validation_report defaults validation status to NOT_VALIDATED."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "validation_report": None,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-validation-status"), "NOT_VALIDATED")

        zf = zipfile.ZipFile(io.BytesIO(resp.content), "r")
        task_toml = zf.read("ctf-task-harbor-1234/task.toml").decode("utf-8")
        self.assertIn('validation_status = "NOT_VALIDATED"', task_toml)

    def test_export_harbor_endpoint_with_validated_report(self):
        """Providing a report with VALIDATED status preserves it in task.toml and headers."""
        validated_report = dict(SAMPLE_VALIDATION_REPORT)
        validated_report["overall_verdict"] = "VALIDATED"
        validated_report["solution_applied_successfully"] = True
        validated_report["negative_test_detected_error"] = True

        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "validation_report": validated_report,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-validation-status"), "VALIDATED")

        zf = zipfile.ZipFile(io.BytesIO(resp.content), "r")
        task_toml = zf.read("ctf-task-harbor-1234/task.toml").decode("utf-8")
        self.assertIn('validation_status = "VALIDATED"', task_toml)

    def test_export_harbor_endpoint_null_starting_commit_sha(self):
        """Gracefully handles null commit SHA, recording empty string in TOML and HEAD in Dockerfile."""
        task_no_sha = dict(SAMPLE_TASK)
        task_no_sha["starting_commit_sha"] = None

        test_suite_no_sha = dict(SAMPLE_TEST_SUITE)
        test_suite_no_sha["repository"] = dict(SAMPLE_TEST_SUITE["repository"])
        test_suite_no_sha["repository"]["starting_commit_sha"] = None

        payload = {
            "task": task_no_sha,
            "solution": SAMPLE_SOLUTION,
            "test_suite": test_suite_no_sha,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 200)

        zf = zipfile.ZipFile(io.BytesIO(resp.content), "r")
        task_toml = zf.read("ctf-task-harbor-1234/task.toml").decode("utf-8")
        self.assertIn('starting_commit_sha = ""', task_toml)

        dockerfile = zf.read("ctf-task-harbor-1234/environment/Dockerfile").decode("utf-8")
        self.assertIn('STARTING_COMMIT_SHA="HEAD"', dockerfile)

    def test_export_harbor_endpoint_custom_task_prefix(self):
        """Applies custom namespace task prefix to filenames and headers."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
            "task_prefix": "eval-track1",
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('filename="eval-track1-task-harbor-1234.zip"', resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.headers.get("x-harbor-task-name"), "eval-track1/task-harbor-1234")

        zf = zipfile.ZipFile(io.BytesIO(resp.content), "r")
        self.assertIn("eval-track1-task-harbor-1234/task.toml", zf.namelist())

    def test_export_harbor_endpoint_rejects_duplicate_solution_paths(self):
        """Duplicate solution paths return 400 Bad Request."""
        dup_solution = dict(SAMPLE_SOLUTION)
        dup_solution["files"] = [
            {
                "path": "app/duplicate.py",
                "status": "create",
                "language": "python",
                "code": "pass",
                "explanation": "first",
            },
            {
                "path": "app/duplicate.py",
                "status": "create",
                "language": "python",
                "code": "pass",
                "explanation": "second duplicate",
            },
        ]

        payload = {
            "task": SAMPLE_TASK,
            "solution": dup_solution,
            "test_suite": SAMPLE_TEST_SUITE,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Duplicate solution file path detected", resp.json()["detail"])

    def test_export_harbor_endpoint_rejects_forbidden_env_file(self):
        """Export request containing forbidden .env file returns 400 Bad Request."""
        env_solution = dict(SAMPLE_SOLUTION)
        env_solution["files"] = [
            {
                "path": ".env",
                "status": "create",
                "language": "text",
                "code": "SECRET=leak",
                "explanation": "leaked secret",
            }
        ]

        payload = {
            "task": SAMPLE_TASK,
            "solution": env_solution,
            "test_suite": SAMPLE_TEST_SUITE,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Forbidden credential/system file", resp.json()["detail"])

    def test_export_harbor_endpoint_rejects_path_traversal(self):
        """Export request with path traversal returns 400 Bad Request."""
        traversal_solution = dict(SAMPLE_SOLUTION)
        traversal_solution["files"] = [
            {
                "path": "app/../../secret.py",
                "status": "create",
                "language": "python",
                "code": "pass",
                "explanation": "traversal attack",
            }
        ]

        payload = {
            "task": SAMPLE_TASK,
            "solution": traversal_solution,
            "test_suite": SAMPLE_TEST_SUITE,
        }

        resp = client.post("/tasks/export/harbor", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Path traversal", resp.json()["detail"])

    def test_export_harbor_endpoint_unexpected_error_returns_500(self):
        """Unexpected internal exceptions return 500 without leaking sensitive paths."""
        payload = {
            "task": SAMPLE_TASK,
            "solution": SAMPLE_SOLUTION,
            "test_suite": SAMPLE_TEST_SUITE,
        }

        with patch("app.services.harbor_service.export_harbor_task_package") as mock_exp:
            mock_exp.side_effect = RuntimeError("Fatal disk failure in C:\\sensitive\\internal\\dir")
            resp = client.post("/tasks/export/harbor", json=payload)

        self.assertEqual(resp.status_code, 502)
        # With RuntimeError, it returns 502 with detail
        # Let's also test an unexpected Exception returns 500 without leaking
        with patch("app.services.harbor_service.export_harbor_task_package") as mock_exp:
            mock_exp.side_effect = Exception("C:\\Users\\admin\\secret_token")
            resp2 = client.post("/tasks/export/harbor", json=payload)

        self.assertEqual(resp2.status_code, 500)
        self.assertNotIn("secret_token", resp2.text)
        self.assertIn("Harbor export failed due to an unexpected server error.", resp2.json()["detail"])

    def test_existing_endpoints_backward_compatibility(self):
        """Existing task listing and health checks remain functional."""
        resp = client.get("/tasks/")
        self.assertEqual(resp.status_code, 200)

        health_resp = client.get("/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json()["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
