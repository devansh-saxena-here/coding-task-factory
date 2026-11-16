"""
Security & Integration tests for repository ingestion (GitHub & ZIP upload).

All external HTTP calls and DNS resolutions are mocked.
Uses unittest.TestCase for full compatibility with Python unittest runner.
"""

import io
import stat
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import repo_service

client = TestClient(app)


def _create_zip_bytes(files: dict[str, str | bytes]) -> bytes:
    """Helper to construct in-memory ZIP archives."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, str):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)
    return buf.getvalue()


# ── SSRF Security Tests ─────────────────────────────────────────────

class TestSSRFProtection(unittest.TestCase):
    def test_rejects_non_https(self):
        resp = client.post("/tasks/analyze/github", json={"repo_url": "http://github.com/owner/repo"})
        self.assertIn(resp.status_code, (400, 422))

    def test_rejects_non_github_host(self):
        resp = client.post("/tasks/analyze/github", json={"repo_url": "https://evil.com/owner/repo"})
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertTrue("Invalid host" in detail or "not a trusted" in detail)

    def test_rejects_loopback_and_internal_hosts(self):
        for host in ["https://127.0.0.1/owner/repo", "https://localhost/owner/repo"]:
            resp = client.post("/tasks/analyze/github", json={"repo_url": host})
            self.assertEqual(resp.status_code, 400)

    @patch("app.services.repo_service.socket.getaddrinfo")
    def test_rejects_private_ip_dns_resolution(self, mock_dns):
        """DNS resolution pointing to a private or loopback IP must be rejected immediately."""
        mock_dns.return_value = [(2, 1, 0, "", ("127.0.0.1", 443))]

        resp = client.post("/tasks/analyze/github", json={"repo_url": "https://github.com/owner/repo"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("disallowed/private IP", resp.json()["detail"])

    @patch("app.services.repo_service._verify_hostname_and_dns")
    @patch("app.services.repo_service.requests.Session.get")
    def test_rejects_malicious_redirect_to_metadata_service(self, mock_get, mock_verify):
        """Redirecting to AWS metadata IP (169.254.169.254) or arbitrary server must be blocked."""
        resp_302 = MagicMock()
        resp_302.status_code = 302
        resp_302.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_get.return_value.__enter__.return_value = resp_302

        def side_effect(host):
            if host != "github.com":
                raise ValueError(f"Host '{host}' is not a trusted GitHub domain.")
        mock_verify.side_effect = side_effect

        resp = client.post("/tasks/analyze/github", json={"repo_url": "https://github.com/owner/repo"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not a trusted GitHub domain", resp.json()["detail"])


# ── ZIP Security & Extraction Tests ─────────────────────────────────

class TestZipSecurity(unittest.TestCase):
    def test_rejects_non_zip_file_upload(self):
        """Uploading plain text or executable disguised as .zip must be rejected via magic bytes."""
        fake_zip = io.BytesIO(b"This is plain text, not a zip file.")
        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("fake.zip", fake_zip, "application/zip")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("valid ZIP magic byte header", resp.json()["detail"])

    def test_rejects_zip_slip_traversal(self):
        """Archives containing relative directory traversal must be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "malicious content")
        bad_zip = buf.getvalue()

        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("slip.zip", io.BytesIO(bad_zip), "application/zip")},
        )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"].lower()
        self.assertTrue("directory traversal" in detail or "traversal" in detail)

    def test_rejects_windows_backslash_traversal(self):
        """Archives containing Windows backslash directory traversal must be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("..\\..\\Windows\\System32\\cmd.exe", "fake")
        bad_zip = buf.getvalue()

        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("win_slip.zip", io.BytesIO(bad_zip), "application/zip")},
        )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"].lower()
        self.assertTrue("directory traversal" in detail or "traversal" in detail)

    def test_rejects_symbolic_links(self):
        """Archives containing POSIX symlinks must be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            info = zipfile.ZipInfo("symlink_entry")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
        symlink_zip = buf.getvalue()

        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("symlink.zip", io.BytesIO(symlink_zip), "application/zip")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Symbolic links", resp.json()["detail"])

    def test_rejects_encrypted_archive(self):
        """Encrypted ZIP archives must be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("secret.txt", "secret data")
        raw = bytearray(buf.getvalue())
        # Set encrypted bit (bit 0) in central directory record
        cd_idx = raw.find(b"PK\x01\x02")
        if cd_idx != -1:
            raw[cd_idx + 8] |= 0x01
        encrypted_zip = bytes(raw)

        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("encrypted.zip", io.BytesIO(encrypted_zip), "application/zip")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Encrypted ZIP", resp.json()["detail"])


# ── Integration Tests ───────────────────────────────────────────────

class TestRepoIngestionEndpoints(unittest.TestCase):
    def test_successful_zip_upload_analysis(self):
        """Valid ZIP upload must parse languages, frameworks, and README."""
        valid_files = {
            "my_project/main.py": "from fastapi import FastAPI\napp = FastAPI()",
            "my_project/requirements.txt": "fastapi==0.162.7\npydantic>=2.0",
            "my_project/README.md": "# Sample Project\nA test project for ingestion.",
        }
        zip_bytes = _create_zip_bytes(valid_files)

        resp = client.post(
            "/tasks/analyze/upload",
            files={"file": ("project.zip", io.BytesIO(zip_bytes), "application/zip")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["source_type"], "zip")
        self.assertIn("Python", data["detected_languages"])
        self.assertIn("FastAPI", data["detected_frameworks"])
        self.assertIn("Pydantic", data["detected_frameworks"])
        self.assertEqual(data["file_count"], 3)
        self.assertIn("Sample Project", data["readme_summary"])

    @patch("app.services.repo_service._verify_hostname_and_dns")
    @patch("app.services.repo_service.requests.Session.get")
    def test_successful_github_analysis(self, mock_get, mock_dns):
        """Mocked successful download of GitHub repository archive."""
        mock_dns.return_value = None

        valid_files = {
            "fastapi-master/main.py": "print('hello')",
            "fastapi-master/README.md": "# FastAPI Master Repo",
        }
        zip_bytes = _create_zip_bytes(valid_files)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [zip_bytes]
        mock_get.return_value.__enter__.return_value = mock_resp

        resp = client.post("/tasks/analyze/github", json={"repo_url": "https://github.com/tiangolo/fastapi"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["source_type"], "github")
        self.assertEqual(data["project_name"], "fastapi")
        self.assertIn("Python", data["detected_languages"])

    @patch("app.services.repo_service._verify_hostname_and_dns")
    @patch("app.services.repo_service.requests.Session.get")
    def test_github_404_private_repo(self, mock_get, mock_dns):
        """404 on GitHub must return HTTP 404."""
        mock_dns.return_value = None

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value.__enter__.return_value = mock_resp

        resp = client.post("/tasks/analyze/github", json={"repo_url": "https://github.com/private/secret-repo"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("was not found or is private", resp.json()["detail"])


# ── Cleanup Guarantee Test ──────────────────────────────────────────

class TestCleanupGuarantee(unittest.TestCase):
    @patch("app.services.repo_service.scan_local_repository")
    def test_temp_directory_cleaned_up_on_failure(self, mock_scan):
        """Temporary directories must be deleted even if scanning raises an exception."""
        mock_scan.side_effect = RuntimeError("Simulated scanner crash")

        valid_files = {"app.py": "print(1)"}
        zip_bytes = _create_zip_bytes(valid_files)

        created_dirs = []
        original_tempdir = repo_service.tempfile.TemporaryDirectory

        class TrackingTempDir(original_tempdir):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created_dirs.append(self.name)

        with patch("app.services.repo_service.tempfile.TemporaryDirectory", TrackingTempDir):
            resp = client.post(
                "/tasks/analyze/upload",
                files={"file": ("crash.zip", io.BytesIO(zip_bytes), "application/zip")},
            )
            self.assertEqual(resp.status_code, 500)

            for d in created_dirs:
                import os
                self.assertFalse(os.path.exists(d), f"Leaked temporary directory: {d}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
