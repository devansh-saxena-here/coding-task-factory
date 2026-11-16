"""
Integration tests for Day 5 Contextual Task Generation endpoints:
- POST /tasks/generate/from-repo
- POST /tasks/generate/github
- POST /tasks/generate/upload

All external HTTP calls (GitHub) and AI calls (Gemini) are mocked.
"""

import io
import json
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


MOCK_TASK_PAYLOAD = {
    "title": "Add Distributed Redis Cache Layer",
    "description": (
        "The project needs an async caching service using Redis to accelerate "
        "read-heavy operations across the FastAPI service."
    ),
    "requirements": [
        "Create app/core/cache.py with get and set methods",
        "Integrate cache dependency in tasks router",
    ],
    "acceptance_criteria": [
        "Given cached data, when fetched, then returns in under 5ms",
    ],
    "relevant_files": [
        "app/routers/tasks.py",
        "app/core/cache.py (new)",
    ],
}


SAMPLE_REPO_ANALYSIS = {
    "project_name": "my-backend-app",
    "source_type": "github",
    "detected_languages": ["Python"],
    "detected_frameworks": ["FastAPI", "Pydantic"],
    "file_count": 8,
    "folder_structure": ["app", "app/routers"],
    "readme_summary": "Sample project README content",
    "analysis_status": "completed",
}


class TestContextualTaskEndpoints(unittest.TestCase):
    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_generate_from_repo_success(self, MockClient):
        """POST /tasks/generate/from-repo returns 201 with TaskResponse."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(MOCK_TASK_PAYLOAD)
        MockClient.return_value.models.generate_content.return_value = mock_resp

        payload = {
            "repo_analysis": SAMPLE_REPO_ANALYSIS,
            "options": {
                "difficulty": "hard",
                "focus_area": "Redis caching",
            },
        }

        resp = client.post("/tasks/generate/from-repo", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["project_name"], "my-backend-app")
        self.assertEqual(data["difficulty"], "hard")
        self.assertEqual(data["title"], MOCK_TASK_PAYLOAD["title"])
        self.assertIn("app/routers/tasks.py", data["relevant_files"])

    @patch("app.services.repo_service._verify_hostname_and_dns")
    @patch("app.services.repo_service.requests.Session.get")
    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_generate_github_success(self, MockClient, mock_get, mock_dns):
        """POST /tasks/generate/github downloads, analyzes, and returns 201 task."""
        mock_dns.return_value = None

        valid_files = {
            "fastapi-master/main.py": "from fastapi import FastAPI\napp = FastAPI()",
            "fastapi-master/requirements.txt": "fastapi==0.162.7",
        }
        zip_bytes = _create_zip_bytes(valid_files)

        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.iter_content.return_value = [zip_bytes]
        mock_get.return_value.__enter__.return_value = mock_http_resp

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = json.dumps(MOCK_TASK_PAYLOAD)
        MockClient.return_value.models.generate_content.return_value = mock_gemini_resp

        payload = {
            "repo_url": "https://github.com/tiangolo/fastapi",
            "options": {"difficulty": "medium"},
        }

        resp = client.post("/tasks/generate/github", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["project_name"], "fastapi")
        self.assertEqual(data["title"], MOCK_TASK_PAYLOAD["title"])
        self.assertIn("app/routers/tasks.py", data["relevant_files"])

    def test_generate_github_invalid_url(self):
        """POST /tasks/generate/github with invalid host returns 400."""
        payload = {
            "repo_url": "https://attacker.com/some/repo",
            "options": {"difficulty": "medium"},
        }
        resp = client.post("/tasks/generate/github", json=payload)
        self.assertEqual(resp.status_code, 400)

    @patch("app.services.repo_service._verify_hostname_and_dns")
    @patch("app.services.repo_service.requests.Session.get")
    def test_generate_github_404_repo(self, mock_get, mock_dns):
        """POST /tasks/generate/github with 404 repo returns 404."""
        mock_dns.return_value = None
        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 404
        mock_get.return_value.__enter__.return_value = mock_http_resp

        payload = {
            "repo_url": "https://github.com/nonexistent/private-repo",
            "options": {"difficulty": "easy"},
        }
        resp = client.post("/tasks/generate/github", json=payload)
        self.assertEqual(resp.status_code, 404)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_generate_upload_success(self, MockClient):
        """POST /tasks/generate/upload with valid ZIP returns 201."""
        valid_files = {
            "my_app/index.js": "const express = require('express');",
            "my_app/package.json": '{"dependencies": {"express": "^4.18.0"}}',
        }
        zip_bytes = _create_zip_bytes(valid_files)

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = json.dumps(MOCK_TASK_PAYLOAD)
        MockClient.return_value.models.generate_content.return_value = mock_gemini_resp

        resp = client.post(
            "/tasks/generate/upload",
            data={"difficulty": "easy", "focus_area": "middleware"},
            files={"file": ("project.zip", io.BytesIO(zip_bytes), "application/zip")},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["project_name"], "project")
        self.assertEqual(data["difficulty"], "easy")
        self.assertEqual(data["title"], MOCK_TASK_PAYLOAD["title"])

    def test_generate_upload_non_zip_file(self):
        """POST /tasks/generate/upload with non-zip extension returns 400."""
        resp = client.post(
            "/tasks/generate/upload",
            files={"file": ("project.tar.gz", io.BytesIO(b"fake data"), "application/gzip")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Only .zip", resp.json()["detail"])

    @patch("app.services.task_service.GEMINI_API_KEY", "")
    def test_generate_from_repo_missing_key(self):
        """Missing GEMINI_API_KEY returns 503 Service Unavailable."""
        payload = {
            "repo_analysis": SAMPLE_REPO_ANALYSIS,
            "options": {"difficulty": "medium"},
        }
        resp = client.post("/tasks/generate/from-repo", json=payload)
        self.assertEqual(resp.status_code, 503)

    @patch("app.services.task_service.genai.Client")
    @patch("app.services.task_service.GEMINI_API_KEY", "fake-test-key")
    def test_generate_from_repo_gemini_failure(self, MockClient):
        """Gemini runtime exception returns 502 Bad Gateway."""
        MockClient.return_value.models.generate_content.side_effect = Exception("Model unavailable")

        payload = {
            "repo_analysis": SAMPLE_REPO_ANALYSIS,
            "options": {"difficulty": "medium"},
        }
        resp = client.post("/tasks/generate/from-repo", json=payload)
        self.assertEqual(resp.status_code, 502)


if __name__ == "__main__":
    unittest.main(verbosity=2)
