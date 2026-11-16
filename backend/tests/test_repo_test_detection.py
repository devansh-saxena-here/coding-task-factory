"""
Unit tests for repo_service.detect_test_framework_and_files() — Day 7 Step 2 (Stream A).

Tests static framework detection, existing test discovery, and unknown fallback behavior
without executing any repository code.
"""

import tempfile
import unittest
from pathlib import Path

from app.services.repo_service import detect_test_framework_and_files


class TestRepoTestDetection(unittest.TestCase):
    """Tests for repository test framework and test file discovery."""

    def test_detect_pytest_via_config_ini(self):
        """Detects pytest via pytest.ini file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_math.py").write_text("def test_add(): assert 1 + 1 == 2\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "pytest")
            self.assertEqual(result["test_framework_config_file"], "pytest.ini")
            self.assertEqual(result["existing_test_files"], ["tests/test_math.py"])

    def test_detect_pytest_via_pyproject_toml(self):
        """Detects pytest via pyproject.toml configuration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\nminversion = '6.0'\n")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_api.py").write_text("def test_get(): pass\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "pytest")
            self.assertEqual(result["test_framework_config_file"], "pyproject.toml")
            self.assertIn("tests/test_api.py", result["existing_test_files"])

    def test_detect_unittest_from_test_imports(self):
        """Detects unittest when test files import unittest without pytest config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_models.py").write_text(
                "import unittest\nclass TestModels(unittest.TestCase):\n    pass\n"
            )

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "unittest")
            self.assertIsNone(result["test_framework_config_file"])
            self.assertEqual(result["existing_test_files"], ["tests/test_models.py"])

    def test_detect_jest_via_jest_config(self):
        """Detects Jest via jest.config.js file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "jest.config.js").write_text("module.exports = { testEnvironment: 'node' };\n")
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "app.test.js").write_text("test('runs', () => expect(1).toBe(1));\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "jest")
            self.assertEqual(result["test_framework_config_file"], "jest.config.js")
            self.assertEqual(result["existing_test_files"], ["src/app.test.js"])

    def test_detect_vitest_via_package_json(self):
        """Detects Vitest via package.json devDependencies."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pkg_json = '{"devDependencies": {"vitest": "^1.0.0"}, "scripts": {"test": "vitest"}}\n'
            (root / "package.json").write_text(pkg_json)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "math.test.ts").write_text("import { test, expect } from 'vitest';\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "vitest")
            self.assertEqual(result["test_framework_config_file"], "package.json")
            self.assertEqual(result["existing_test_files"], ["tests/math.test.ts"])

    def test_detect_mocha_via_mocharc(self):
        """Detects Mocha via .mocharc.json config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".mocharc.json").write_text('{"extension": ["js"]}\n')
            test_dir = root / "test"
            test_dir.mkdir()
            (test_dir / "user.spec.js").write_text("describe('User', () => {});\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "mocha")
            self.assertEqual(result["test_framework_config_file"], ".mocharc.json")
            self.assertEqual(result["existing_test_files"], ["test/user.spec.js"])

    def test_detect_go_test_from_test_files(self):
        """Detects go test from *_test.go files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "go.mod").write_text("module example.com/calc\n\ngo 1.21\n")
            (root / "calc_test.go").write_text("package calc\n\nimport 'testing'\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "go test")
            self.assertEqual(result["existing_test_files"], ["calc_test.go"])

    def test_unknown_framework_when_no_tests_or_configs(self):
        """Returns 'unknown' with empty test files list when no test evidence exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "main.py").write_text("print('hello world')\n")
            (root / "utils.py").write_text("def helper(): return True\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["test_framework"], "unknown")
            self.assertIsNone(result["test_framework_config_file"])
            self.assertEqual(result["existing_test_files"], [])

    def test_ignored_directories_not_scanned_for_tests(self):
        """Ensures test files inside node_modules, .venv, or .git are strictly ignored."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            venv_tests = root / ".venv" / "lib" / "tests"
            venv_tests.mkdir(parents=True)
            (venv_tests / "test_internal.py").write_text("def test_lib(): pass\n")

            node_tests = root / "node_modules" / "pkg" / "__tests__"
            node_tests.mkdir(parents=True)
            (node_tests / "pkg.test.js").write_text("test('x', () => {});\n")

            # Root valid test
            (root / "test_app.py").write_text("def test_app(): pass\n")

            result = detect_test_framework_and_files(root)
            self.assertEqual(result["existing_test_files"], ["test_app.py"])

    def test_nonexistent_directory_raises_value_error(self):
        """Raises ValueError when given a non-existent path."""
        with self.assertRaises(ValueError):
            detect_test_framework_and_files("/path/that/does/not/exist/999")


if __name__ == "__main__":
    unittest.main()
