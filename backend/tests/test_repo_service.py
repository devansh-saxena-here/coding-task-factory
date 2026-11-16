"""
Unit tests for repo_service.scan_local_repository.

Creates temporary mock project directories and asserts:
- Language detection via file extensions
- Framework detection via config files
- Ignored directories (.git, .venv, node_modules, etc.)
- Ignored binary/media file extensions
- README extraction & truncation
- File counting
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.schemas.repo import RepoAnalysisResponse
from app.services import repo_service


class TestRepoScanner(unittest.TestCase):
    def setUp(self):
        # Create a fresh temporary directory for each test
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        # Clean up temporary directory after each test
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_language_detection(self):
        """Verify file extensions map to detected programming languages."""
        (self.root / "main.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "utils.py").write_text("def util(): pass", encoding="utf-8")
        (self.root / "app.ts").write_text("const x: number = 1;", encoding="utf-8")
        (self.root / "index.js").write_text("console.log('hi');", encoding="utf-8")

        result = repo_service.scan_local_repository(self.root, project_name="test-repo")

        self.assertIsInstance(result, RepoAnalysisResponse)
        # Python has 2 files, so it should be ranked first
        self.assertEqual(result.detected_languages[0], "Python")
        self.assertIn("TypeScript", result.detected_languages)
        self.assertIn("JavaScript", result.detected_languages)
        self.assertEqual(result.file_count, 4)

    def test_framework_detection_python(self):
        """Verify Python framework detection via requirements.txt."""
        reqs = "fastapi==0.162.7\nuvicorn==0.54.0\npydantic>=2.0\npytest\n"
        (self.root / "requirements.txt").write_text(reqs, encoding="utf-8")

        result = repo_service.scan_local_repository(self.root)
        self.assertIn("FastAPI", result.detected_frameworks)
        self.assertIn("Pydantic", result.detected_frameworks)
        self.assertIn("Pytest", result.detected_frameworks)

    def test_framework_detection_javascript(self):
        """Verify JS framework detection via package.json."""
        pkg = {
            "name": "my-frontend",
            "dependencies": {
                "react": "^18.2.0",
                "next": "^14.0.0",
                "tailwindcss": "^3.0.0"
            },
            "devDependencies": {
                "express": "^4.18.0"
            }
        }
        (self.root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

        result = repo_service.scan_local_repository(self.root)
        self.assertIn("React", result.detected_frameworks)
        self.assertIn("Next.js", result.detected_frameworks)
        self.assertIn("Tailwind CSS", result.detected_frameworks)
        self.assertIn("Express", result.detected_frameworks)

    def test_ignored_directories(self):
        """Ensure .git, .venv, node_modules, and __pycache__ are ignored."""
        # Valid file
        (self.root / "main.py").write_text("print('ok')", encoding="utf-8")

        # Files inside ignored dirs
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config", encoding="utf-8")

        venv_dir = self.root / ".venv" / "Lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "lib.py").write_text("pass", encoding="utf-8")

        nm_dir = self.root / "node_modules" / "pkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_text("pass", encoding="utf-8")

        pycache_dir = self.root / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "main.cpython-314.pyc").write_bytes(b"\x00\x01\x02")

        result = repo_service.scan_local_repository(self.root)

        # Only main.py should be counted
        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.detected_languages, ["Python"])
        for folder in result.folder_structure:
            self.assertNotIn(".git", folder)
            self.assertNotIn(".venv", folder)
            self.assertNotIn("node_modules", folder)
            self.assertNotIn("__pycache__", folder)

    def test_ignored_binary_extensions(self):
        """Ensure media, archive, and executable files are excluded from scan count."""
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "app.exe").write_bytes(b"MZ\x90\x00")
        (self.root / "archive.zip").write_bytes(b"PK\x03\x04")
        (self.root / "script.py").write_text("print('hello')", encoding="utf-8")

        result = repo_service.scan_local_repository(self.root)
        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.detected_languages, ["Python"])

    def test_readme_extraction_and_truncation(self):
        """Verify README is read and truncated if it exceeds maximum character limit."""
        long_content = "A" * 3000
        (self.root / "README.md").write_text(long_content, encoding="utf-8")

        result = repo_service.scan_local_repository(self.root)
        self.assertIsNotNone(result.readme_summary)
        self.assertTrue(result.readme_summary.endswith("...(truncated)"))
        # Truncated length should be around MAX_README_CHARS + truncated indicator length
        self.assertLess(len(result.readme_summary), 2100)

    def test_nonexistent_directory(self):
        """Verify error is raised when passing an invalid directory."""
        fake_path = self.root / "does_not_exist"
        with self.assertRaises(ValueError):
            repo_service.scan_local_repository(fake_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
