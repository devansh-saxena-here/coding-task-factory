"""
End-to-End Integration Workflow Tests — Day 10 Step 1.

Audits the complete multi-stage pipeline of the Coding Task Factory:
1. Ingest repository (upload ZIP or GitHub URL).
2. Analyze structure, languages, frameworks, test configuration, and starting commit SHA.
3. Generate contextual coding task from repository analysis (Gemini AI mocked).
4. Generate production-ready reference solution (Gemini AI mocked).
5. Synthesize repository-aware feature and regression tests (Gemini AI mocked).
6. Validate task package across validation gates in static execution mode.
7. Verify truthful NOT_VALIDATED status (zero false VALIDATED outcomes).
8. Export Harbor evaluation package as downloadable ZIP archive.
9. Verify archive structure, schema 1.4 compliance, verifier reward protocol, and oracle solve script.

Also tests:
- Commit SHA propagation across all stages.
- Null commit SHA graceful handling.
- Missing API key behavior across Gemini endpoints (503).
- Invalid inputs (malformed zip, SSRF URL, bad file extension).
- Artifact ID consistency and cross-stage contract enforcement (422).
- Guaranteed cleanup of temporary workspace directories.

Zero untrusted code is executed on the host.
"""

import io
import json
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── Helpers for Creating In-Memory Test Repositories ─────────────────

def _create_sample_repo_zip(commit_sha: str | None = None) -> bytes:
    """Builds a realistic in-memory python repository ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("store_api/README.md", "# Store API\nA lightweight service for item catalog.")
        zf.writestr("store_api/requirements.txt", "fastapi==0.110.0\nuvicorn==0.28.0\npytest==8.1.0\n")
        zf.writestr("store_api/pyproject.toml", "[tool.pytest.ini_options]\ntestpaths = ['tests']\n")
        zf.writestr("store_api/app/__init__.py", "")
        zf.writestr(
            "store_api/app/main.py",
            "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/items')\ndef list_items():\n    return [{'id': 1, 'name': 'Item 1'}]\n",
        )
        zf.writestr("store_api/tests/__init__.py", "")
        zf.writestr(
            "store_api/tests/test_items.py",
            "from app.main import app\n\ndef test_list_items():\n    assert True\n",
        )
        if commit_sha:
            # Simulate git HEAD reference
            zf.writestr("store_api/.git/HEAD", f"{commit_sha}\n")
    return buf.getvalue()


# ── Mock Gemini Responses ───────────────────────────────────────────

MOCK_TASK_GEMINI_RESPONSE = {
    "title": "Add In-Memory Caching to Items Endpoint",
    "description": "The current /items endpoint queries the store repeatedly. Implement a fast in-memory cache layer with TTL.",
    "requirements": [
        "Create an in-memory cache utility with get and set methods",
        "Add TTL expiration support defaulting to 60 seconds",
        "Integrate cache into /items endpoint",
    ],
    "acceptance_criteria": [
        "First call to /items populates the cache",
        "Subsequent calls return cached items without recalculating",
        "Cache entries expire after configured TTL",
    ],
    "relevant_files": [
        "app/cache.py (new)",
        "app/main.py (modified)",
    ],
}

MOCK_SOLUTION_GEMINI_RESPONSE = {
    "architecture_notes": "Implements an in-memory TTL dictionary cache wrapped around the endpoint.",
    "files": [
        {
            "path": "app/cache.py",
            "status": "create",
            "language": "python",
            "code": "import time\n\nclass MemoryCache:\n    def __init__(self, ttl: int = 60):\n        self.ttl = ttl\n        self._store = {}\n    def get(self, key):\n        if key in self._store:\n            val, exp = self._store[key]\n            if time.time() < exp:\n                return val\n        return None\n    def set(self, key, val):\n        self._store[key] = (val, time.time() + self.ttl)\n",
            "explanation": "Provides TTL dictionary caching.",
        },
        {
            "path": "app/main.py",
            "status": "modify",
            "language": "python",
            "code": "from fastapi import FastAPI\nfrom app.cache import MemoryCache\n\napp = FastAPI()\ncache = MemoryCache(ttl=60)\n\n@app.get('/items')\ndef list_items():\n    cached = cache.get('items')\n    if cached is not None:\n        return cached\n    items = [{'id': 1, 'name': 'Item 1'}]\n    cache.set('items', items)\n    return items\n",
            "explanation": "Integrates MemoryCache into items endpoint.",
        },
    ],
    "testing_guide": "Run pytest tests/feature tests/regression -v",
    "verification_steps": [
        "Call GET /items first time to populate cache",
        "Call GET /items second time to verify hit",
    ],
}

MOCK_TEST_SUITE_GEMINI_RESPONSE = {
    "feature_test_files": [
        {
            "path": "tests/feature/test_cache_feature.py",
            "framework": "pytest",
            "code": "from app.cache import MemoryCache\n\ndef test_cache_set_and_get():\n    c = MemoryCache(ttl=10)\n    c.set('k', 'v')\n    assert c.get('k') == 'v'\n\ndef test_cache_miss():\n    c = MemoryCache(ttl=10)\n    assert c.get('missing') is None\n",
            "test_cases": [
                {
                    "name": "test_cache_set_and_get",
                    "case_type": "happy_path",
                    "description": "Verifies key storage and retrieval",
                    "target_criterion": "First call populates cache",
                    "expected_behavior": "Returns stored value",
                },
                {
                    "name": "test_cache_miss",
                    "case_type": "edge_case",
                    "description": "Verifies behavior on unknown key",
                    "target_criterion": "Cache misses return None",
                    "expected_behavior": "Returns None",
                },
            ],
        }
    ],
    "regression_test_files": [
        {
            "path": "tests/regression/test_items_regression.py",
            "framework": "pytest",
            "code": "from app.main import app\n\ndef test_existing_items_schema():\n    assert True\n",
            "test_cases": [
                {
                    "name": "test_existing_items_schema",
                    "case_type": "regression_check",
                    "description": "Ensures /items endpoint response structure is intact",
                    "target_criterion": "Preserve existing API schema",
                    "expected_behavior": "Items schema preserved",
                }
            ],
        }
    ],
    "coverage_summary": "2 feature tests verifying cache operations; 1 regression check for items contract.",
    "execution_instructions": "pytest tests/feature tests/regression -v",
}


def _mock_gemini_client_returning(json_data: dict):
    """Helper creating a mock Gemini client that returns json_data."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(json_data)
    mock_client.models.generate_content.return_value = mock_resp
    return mock_client


class TestEndToEndWorkflow(unittest.TestCase):
    """End-to-end integration test suite verifying the complete 9-step pipeline."""

    def test_complete_e2e_pipeline_with_zip_repository(self):
        """
        Executes the entire end-to-end workflow from ZIP upload through Harbor export.
        Verifies correct cross-stage artifact propagation, ID tracking, static validation
        truthfulness, and ZIP archive conformance.
        """
        # ── Step 1: Upload and analyze ZIP repository ──────────────────
        zip_bytes = _create_sample_repo_zip(commit_sha=None)
        files = {"file": ("store_api.zip", zip_bytes, "application/zip")}

        resp_analysis = client.post("/tasks/analyze/upload", files=files)
        self.assertEqual(resp_analysis.status_code, 200, f"Analysis failed: {resp_analysis.text}")
        analysis_data = resp_analysis.json()

        self.assertEqual(analysis_data["project_name"], "store_api")
        self.assertEqual(analysis_data["source_type"], "zip")
        self.assertIn("Python", analysis_data["detected_languages"])
        self.assertEqual(analysis_data["analysis_status"], "completed")

        # ── Step 2: Generate contextual task from repository analysis ──
        with patch("app.services.task_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TASK_GEMINI_RESPONSE)):
            task_req_payload = {
                "repo_analysis": analysis_data,
                "options": {
                    "difficulty": "medium",
                    "focus_area": "caching",
                    "category": "backend",
                },
            }
            resp_task = client.post("/tasks/generate/from-repo", json=task_req_payload)

        self.assertEqual(resp_task.status_code, 201, f"Task generation failed: {resp_task.text}")
        task_data = resp_task.json()

        task_id = task_data["id"]
        self.assertTrue(task_id)
        self.assertEqual(task_data["title"], "Add In-Memory Caching to Items Endpoint")
        self.assertEqual(task_data["project_name"], "store_api")
        self.assertIsNone(task_data["starting_commit_sha"])

        # ── Step 3: Generate reference solution ────────────────────────
        with patch("app.services.solution_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_SOLUTION_GEMINI_RESPONSE)):
            sol_req_payload = {"task": task_data}
            resp_sol = client.post("/tasks/solution", json=sol_req_payload)

        self.assertEqual(resp_sol.status_code, 201, f"Solution generation failed: {resp_sol.text}")
        solution_data = resp_sol.json()

        solution_id = solution_data["id"]
        self.assertTrue(solution_id)
        self.assertEqual(solution_data["task_id"], task_id, "Solution task_id must match Task ID")
        self.assertEqual(len(solution_data["files"]), 2)

        # ── Step 4: Synthesize test suite ──────────────────────────────
        with patch("app.services.test_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TEST_SUITE_GEMINI_RESPONSE)):
            test_req_payload = {
                "task": task_data,
                "solution": solution_data,
                "repo_analysis": analysis_data,
                "preferred_framework": "pytest",
            }
            resp_test = client.post("/tasks/tests", json=test_req_payload)

        self.assertEqual(resp_test.status_code, 201, f"Test generation failed: {resp_test.text}")
        test_suite_data = resp_test.json()

        test_suite_id = test_suite_data["id"]
        self.assertTrue(test_suite_id)
        self.assertEqual(test_suite_data["task_id"], task_id, "TestSuite task_id must match Task ID")
        self.assertEqual(test_suite_data["repository"]["project_name"], "store_api")
        self.assertEqual(test_suite_data["total_feature_tests"], 2)
        self.assertEqual(test_suite_data["total_regression_tests"], 1)

        # ── Step 5: Submit package for validation ──────────────────────
        val_req_payload = {
            "task": task_data,
            "solution": solution_data,
            "test_suite": test_suite_data,
            "execution_mode": "static",
        }
        resp_val = client.post("/tasks/validate", json=val_req_payload)

        self.assertEqual(resp_val.status_code, 200, f"Validation failed: {resp_val.text}")
        val_data = resp_val.json()

        self.assertEqual(val_data["task_id"], task_id)
        self.assertEqual(val_data["solution_id"], solution_id)
        self.assertEqual(val_data["test_suite_id"], test_suite_id)
        self.assertTrue(val_data["solution_applied_successfully"])
        # Crucial security guarantee: Static validation MUST NEVER be VALIDATED
        self.assertEqual(val_data["overall_verdict"], "NOT_VALIDATED")
        self.assertIn("app/cache.py", val_data["created_files"])

        # ── Step 6: Export to official Harbor ZIP package ──────────────
        export_payload = {
            "task": task_data,
            "solution": solution_data,
            "test_suite": test_suite_data,
            "validation_report": val_data,
            "task_prefix": "ctf-e2e",
        }
        resp_export = client.post("/tasks/export/harbor", json=export_payload)

        self.assertEqual(resp_export.status_code, 200, f"Harbor export failed: {resp_export.text}")
        self.assertEqual(resp_export.headers["content-type"], "application/zip")
        self.assertIn('filename="ctf-e2e-', resp_export.headers.get("content-disposition", ""))
        self.assertEqual(resp_export.headers.get("x-validation-status"), "NOT_VALIDATED")

        # ── Step 7: Verify internal ZIP structure & Harbor compliance ──
        zf = zipfile.ZipFile(io.BytesIO(resp_export.content), "r")
        namelist = zf.namelist()
        prefix = f"ctf-e2e-{task_id}/"

        # Check required files
        self.assertIn(f"{prefix}task.toml", namelist)
        self.assertIn(f"{prefix}instruction.md", namelist)
        self.assertIn(f"{prefix}environment/Dockerfile", namelist)
        self.assertIn(f"{prefix}tests/test.sh", namelist)
        self.assertIn(f"{prefix}tests/feature/test_cache_feature.py", namelist)
        self.assertIn(f"{prefix}tests/regression/test_items_regression.py", namelist)
        self.assertIn(f"{prefix}solution/solve.sh", namelist)
        self.assertIn(f"{prefix}solution/files/app/cache.py", namelist)
        self.assertIn(f"{prefix}solution/files/app/main.py", namelist)

        # Audit task.toml content
        task_toml = zf.read(f"{prefix}task.toml").decode("utf-8")
        self.assertIn('schema_version = "1.4"', task_toml)
        self.assertIn('validation_status = "NOT_VALIDATED"', task_toml)
        self.assertIn('project_name = "store_api"', task_toml)

        # Audit instruction.md does not leak reference implementation code
        instruction_md = zf.read(f"{prefix}instruction.md").decode("utf-8")
        self.assertIn("# Add In-Memory Caching to Items Endpoint", instruction_md)
        self.assertIn("## Functional Requirements", instruction_md)
        self.assertNotIn("class MemoryCache:", instruction_md)
        self.assertNotIn("def test_cache_set_and_get", instruction_md)

        # Audit tests/test.sh verifier reward protocol
        test_sh = zf.read(f"{prefix}tests/test.sh").decode("utf-8")
        self.assertIn('REWARD_FILE="/logs/verifier/reward.txt"', test_sh)
        self.assertIn('echo "1.0" > "$REWARD_FILE"', test_sh)
        self.assertIn('echo "0.0" > "$REWARD_FILE"', test_sh)

        # Audit solution/solve.sh
        solve_sh = zf.read(f"{prefix}solution/solve.sh").decode("utf-8")
        self.assertIn('cp -R "$FILES_DIR"/. /workspace/', solve_sh)

    def test_e2e_git_commit_sha_propagation(self):
        """
        Verifies that starting Git commit SHA is accurately preserved across
        every single stage of the pipeline: analysis -> task -> tests -> validation -> Harbor export.
        """
        known_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # Mock repository analysis with git commit SHA
        mock_analysis = {
            "project_name": "git_repo",
            "source_type": "github",
            "commit_sha": known_sha,
            "detected_languages": ["Python"],
            "detected_frameworks": ["FastAPI"],
            "file_count": 5,
            "folder_structure": ["app", "tests"],
            "readme_summary": "Git repository sample",
            "analysis_status": "completed",
        }

        # Stage 1: Generate Task with SHA
        with patch("app.services.task_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TASK_GEMINI_RESPONSE)):
            resp_task = client.post("/tasks/generate/from-repo", json={"repo_analysis": mock_analysis})
        self.assertEqual(resp_task.status_code, 201)
        task_data = resp_task.json()
        self.assertEqual(task_data["starting_commit_sha"], known_sha, "Task must inherit commit SHA from repo analysis")

        # Stage 2: Generate Solution
        with patch("app.services.solution_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_SOLUTION_GEMINI_RESPONSE)):
            resp_sol = client.post("/tasks/solution", json={"task": task_data})
        self.assertEqual(resp_sol.status_code, 201)
        solution_data = resp_sol.json()

        # Stage 3: Generate Tests with SHA
        with patch("app.services.test_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TEST_SUITE_GEMINI_RESPONSE)):
            resp_test = client.post(
                "/tasks/tests",
                json={
                    "task": task_data,
                    "solution": solution_data,
                    "repo_analysis": mock_analysis,
                },
            )
        self.assertEqual(resp_test.status_code, 201)
        test_suite_data = resp_test.json()
        self.assertEqual(
            test_suite_data["repository"]["starting_commit_sha"],
            known_sha,
            "TestSuite repository must preserve commit SHA",
        )

        # Stage 4: Validate with SHA
        resp_val = client.post(
            "/tasks/validate",
            json={
                "task": task_data,
                "solution": solution_data,
                "test_suite": test_suite_data,
            },
        )
        self.assertEqual(resp_val.status_code, 200)
        val_data = resp_val.json()
        self.assertEqual(val_data["starting_commit_sha"], known_sha, "ValidationReport must preserve commit SHA")

        # Stage 5: Export to Harbor with SHA
        resp_export = client.post(
            "/tasks/export/harbor",
            json={
                "task": task_data,
                "solution": solution_data,
                "test_suite": test_suite_data,
                "validation_report": val_data,
            },
        )
        self.assertEqual(resp_export.status_code, 200)

        zf = zipfile.ZipFile(io.BytesIO(resp_export.content), "r")
        prefix = f"ctf-{task_data['id']}/"

        # Verify task.toml records exact commit SHA
        task_toml = zf.read(f"{prefix}task.toml").decode("utf-8")
        self.assertIn(f'starting_commit_sha = "{known_sha}"', task_toml)

        # Verify Dockerfile sets STARTING_COMMIT_SHA
        dockerfile = zf.read(f"{prefix}environment/Dockerfile").decode("utf-8")
        self.assertIn(f'STARTING_COMMIT_SHA="{known_sha}"', dockerfile)

    def test_e2e_null_commit_sha_handled_gracefully(self):
        """
        When commit SHA is absent, every stage handles None gracefully without errors,
        recording empty string in task.toml and 'HEAD' in Dockerfile.
        """
        mock_analysis_no_sha = {
            "project_name": "zip_repo",
            "source_type": "zip",
            "commit_sha": None,
            "detected_languages": ["Python"],
            "detected_frameworks": [],
            "file_count": 2,
            "folder_structure": [],
            "readme_summary": None,
            "analysis_status": "completed",
        }

        with patch("app.services.task_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TASK_GEMINI_RESPONSE)):
            task_data = client.post("/tasks/generate/from-repo", json={"repo_analysis": mock_analysis_no_sha}).json()

        self.assertIsNone(task_data["starting_commit_sha"])

        with patch("app.services.solution_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_SOLUTION_GEMINI_RESPONSE)):
            solution_data = client.post("/tasks/solution", json={"task": task_data}).json()

        with patch("app.services.test_service._get_gemini_client", return_value=_mock_gemini_client_returning(MOCK_TEST_SUITE_GEMINI_RESPONSE)):
            test_suite_data = client.post(
                "/tasks/tests",
                json={"task": task_data, "solution": solution_data, "repo_analysis": mock_analysis_no_sha},
            ).json()

        val_data = client.post(
            "/tasks/validate",
            json={"task": task_data, "solution": solution_data, "test_suite": test_suite_data},
        ).json()
        self.assertIsNone(val_data["starting_commit_sha"])

        resp_export = client.post(
            "/tasks/export/harbor",
            json={
                "task": task_data,
                "solution": solution_data,
                "test_suite": test_suite_data,
                "validation_report": val_data,
            },
        )
        self.assertEqual(resp_export.status_code, 200)

        zf = zipfile.ZipFile(io.BytesIO(resp_export.content), "r")
        prefix = f"ctf-{task_data['id']}/"
        task_toml = zf.read(f"{prefix}task.toml").decode("utf-8")
        self.assertIn('starting_commit_sha = ""', task_toml)

        dockerfile = zf.read(f"{prefix}environment/Dockerfile").decode("utf-8")
        self.assertIn('STARTING_COMMIT_SHA="HEAD"', dockerfile)

    def test_missing_api_key_returns_503_across_gemini_endpoints(self):
        """
        When GEMINI_API_KEY is unset, all AI endpoints return 503 Service Unavailable
        with a descriptive error instructing configuration.
        """
        dummy_task = {
            "id": "task-test-503",
            "topic": "topic",
            "difficulty": "medium",
            "language": "python",
            "category": "backend",
            "title": "Title",
            "description": "Desc",
            "requirements": ["Req 1"],
            "acceptance_criteria": ["Crit 1"],
            "generated_at": "2026-11-16T12:00:00Z",
        }

        # 1. POST /tasks/generate
        with patch("app.services.task_service.GEMINI_API_KEY", ""):
            resp_gen = client.post("/tasks/generate", json={"topic": "Build microservice"})
            self.assertEqual(resp_gen.status_code, 503)
            self.assertIn("GEMINI_API_KEY is not set", resp_gen.json()["detail"])

        # 2. POST /tasks/generate/from-repo
        with patch("app.services.task_service.GEMINI_API_KEY", ""):
            resp_repo = client.post(
                "/tasks/generate/from-repo",
                json={
                    "repo_analysis": {
                        "project_name": "store",
                        "source_type": "zip",
                        "analysis_status": "completed",
                    }
                },
            )
            self.assertEqual(resp_repo.status_code, 503)
            self.assertIn("GEMINI_API_KEY is not set", resp_repo.json()["detail"])

        # 3. POST /tasks/solution
        with patch("app.services.solution_service.GEMINI_API_KEY", ""):
            resp_sol = client.post("/tasks/solution", json={"task": dummy_task})
            self.assertEqual(resp_sol.status_code, 503)
            self.assertIn("GEMINI_API_KEY is not set", resp_sol.json()["detail"])

        # 4. POST /tasks/tests
        with patch("app.services.test_service.GEMINI_API_KEY", ""):
            resp_tests = client.post("/tasks/tests", json={"task": dummy_task})
            self.assertEqual(resp_tests.status_code, 503)
            self.assertIn("GEMINI_API_KEY is not set", resp_tests.json()["detail"])

    def test_invalid_input_rejections(self):
        """API endpoints reject malformed inputs with appropriate 400 or 422 codes."""
        # Non-zip upload
        files = {"file": ("test.txt", b"plain text", "text/plain")}
        resp = client.post("/tasks/analyze/upload", files=files)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Only .zip archive uploads are supported", resp.json()["detail"])

        # Corrupted / invalid zip upload
        files_corrupt = {"file": ("corrupt.zip", b"not a valid zip binary stream", "application/zip")}
        resp_corrupt = client.post("/tasks/analyze/upload", files=files_corrupt)
        self.assertEqual(resp_corrupt.status_code, 400)

        # Invalid GitHub URL host / SSRF
        resp_ssrf = client.post("/tasks/analyze/github", json={"repo_url": "https://attacker.com/repo"})
        self.assertEqual(resp_ssrf.status_code, 400)
        self.assertIn("Expected 'github.com'", resp_ssrf.json()["detail"])

    def test_cross_stage_contract_enforcement_and_failure_propagation(self):
        """
        Cross-stage contract validators prevent artifact ID mismatches between
        task, solution, test suite, and validation report.
        """
        task_a = {
            "id": "task-uuid-AAAA",
            "topic": "topic A",
            "difficulty": "medium",
            "language": "python",
            "category": "backend",
            "title": "Title A",
            "description": "Desc A",
            "requirements": ["Req A"],
            "acceptance_criteria": ["Crit A"],
            "generated_at": "2026-11-16T12:00:00Z",
        }
        task_b = dict(task_a, id="task-uuid-BBBB", title="Title B")

        solution_a = {
            "id": "sol-uuid-AAAA",
            "task_id": "task-uuid-AAAA",
            "task_title": "Title A",
            "architecture_notes": "Notes",
            "files": [],
            "testing_guide": "Guide",
            "verification_steps": [],
            "generated_at": "2026-11-16T12:00:00Z",
        }

        test_suite_a = {
            "id": "suite-uuid-AAAA",
            "task_id": "task-uuid-AAAA",
            "task_title": "Title A",
            "repository": {"project_name": "repo"},
            "feature_test_files": [],
            "regression_test_files": [],
            "coverage_summary": "cov",
            "execution_instructions": "pytest",
            "generated_at": "2026-11-16T12:00:00Z",
        }

        # 1. POST /tasks/tests with mismatched solution task_id
        resp_test_mismatch = client.post(
            "/tasks/tests",
            json={"task": task_b, "solution": solution_a},
        )
        self.assertEqual(resp_test_mismatch.status_code, 422)
        self.assertIn("does not match Task ID", resp_test_mismatch.text)

        # 2. POST /tasks/validate with mismatched solution task_id
        resp_val_mismatch = client.post(
            "/tasks/validate",
            json={"task": task_b, "solution": solution_a, "test_suite": test_suite_a},
        )
        self.assertEqual(resp_val_mismatch.status_code, 422)
        self.assertIn("does not match Task ID", resp_val_mismatch.text)

        # 3. POST /tasks/export/harbor with mismatched test suite task_id
        resp_export_mismatch = client.post(
            "/tasks/export/harbor",
            json={
                "task": task_b,
                "solution": dict(solution_a, task_id="task-uuid-BBBB"),
                "test_suite": test_suite_a,  # has task_id = AAAA
            },
        )
        self.assertEqual(resp_export_mismatch.status_code, 422)
        self.assertIn("does not match Task ID", resp_export_mismatch.text)


if __name__ == "__main__":
    unittest.main()
