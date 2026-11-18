"""
Sample Harbor Task Exporter Script — Day 12 Step 3.

Generates a deterministic, self-contained Python sample task package
using the official Coding Task Factory Harbor exporter.
No external Gemini or third-party API calls are made.
Zero untrusted code is executed on the host.
"""

import argparse
import json
from pathlib import Path
import sys
import zipfile

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.schemas.harbor import HarborEnvironmentConfig, HarborExportRequest
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestCase, TestFile, TestSuiteResponse
from app.services.harbor_service import export_harbor_task_package


def build_sample_task_payload() -> HarborExportRequest:
    """Creates a deterministic, validated math utilities task package payload."""
    task_id = "sample-math-task"
    commit_sha = "e4d909c290d0fb1ca068ffaddf22cbd0addd4b76"

    task = TaskResponse(
        id=task_id,
        topic="Core Utilities: Arithmetic Functions",
        title="Implement Basic Math Utilities",
        description="Implement add and multiply functions in calc.py to provide core mathematical operations.",
        difficulty="easy",
        language="python",
        category="backend",
        requirements=[
            "Implement add(a, b) returning the arithmetic sum",
            "Implement multiply(a, b) returning the arithmetic product",
        ],
        acceptance_criteria=[
            "add(2, 3) returns 5",
            "multiply(4, 5) returns 20",
        ],
        relevant_files=["calc.py (new)"],
        starting_commit_sha=commit_sha,
        project_name="math_utils",
        generated_at="2026-11-17T12:00:00Z",
    )

    solution_code = '''"""Basic math utility functions."""

def add(a: int | float, b: int | float) -> int | float:
    """Return the sum of a and b."""
    return a + b


def multiply(a: int | float, b: int | float) -> int | float:
    """Return the product of a and b."""
    return a * b
'''

    solution = SolutionResponse(
        id="sol-sample-math",
        task_id=task_id,
        task_title="Implement Basic Math Utilities",
        architecture_notes="Provides pure, standalone functional arithmetic helpers.",
        files=[
            SolutionFile(
                path="calc.py",
                status="create",
                language="python",
                code=solution_code,
                explanation="Implements addition and multiplication helpers.",
            )
        ],
        testing_guide="Run pytest /tests/feature /tests/regression -v",
        verification_steps=["Verify pytest passes"],
        generated_at="2026-11-17T12:05:00Z",
    )

    feature_test_code = '''import sys
sys.path.insert(0, "/workspace")

import pytest
from calc import add, multiply


def test_add_positive_numbers():
    assert add(2, 3) == 5


def test_multiply_positive_numbers():
    assert multiply(4, 5) == 20
'''

    regression_test_code = '''import sys
sys.path.insert(0, "/workspace")

import pytest
from calc import add, multiply


def test_add_zero():
    assert add(0, 0) == 0


def test_multiply_by_zero():
    assert multiply(10, 0) == 0
'''

    test_suite = TestSuiteResponse(
        id="suite-sample-math",
        task_id=task_id,
        task_title="Implement Basic Math Utilities",
        repository=RepositoryMetadata(
            project_name="math_utils",
            source_type="local",
            starting_commit_sha=commit_sha,
            detected_language="python",
            test_framework="pytest",
        ),
        feature_test_files=[
            TestFile(
                path="tests/test_feature_math.py",
                test_kind="feature",
                framework="pytest",
                code=feature_test_code,
                test_cases=[
                    TestCase(
                        name="test_add_positive_numbers",
                        test_kind="feature",
                        case_type="happy_path",
                        description="Test addition of two positive integers",
                        target_criterion="add(2, 3) returns 5",
                        expected_behavior="Returns 5",
                    ),
                    TestCase(
                        name="test_multiply_positive_numbers",
                        test_kind="feature",
                        case_type="happy_path",
                        description="Test multiplication of two positive integers",
                        target_criterion="multiply(4, 5) returns 20",
                        expected_behavior="Returns 20",
                    ),
                ],
            )
        ],
        regression_test_files=[
            TestFile(
                path="tests/test_regression_math.py",
                test_kind="regression",
                framework="pytest",
                code=regression_test_code,
                test_cases=[
                    TestCase(
                        name="test_add_zero",
                        test_kind="regression",
                        case_type="regression_check",
                        description="Test zero addition identity",
                        target_criterion="Pre-existing baseline math preserved",
                        expected_behavior="Returns 0",
                    ),
                    TestCase(
                        name="test_multiply_by_zero",
                        test_kind="regression",
                        case_type="regression_check",
                        description="Test multiplication by zero absorbs product",
                        target_criterion="Pre-existing baseline math preserved",
                        expected_behavior="Returns 0",
                    ),
                ],
            )
        ],
        total_feature_tests=2,
        total_regression_tests=2,
        coverage_summary="Feature coverage: add, multiply. Regression coverage: identity laws.",
        execution_instructions="pytest /tests/feature /tests/regression -v",
        generated_at="2026-11-17T12:10:00Z",
    )

    return HarborExportRequest(
        task=task,
        solution=solution,
        test_suite=test_suite,
        validation_report=None,
        task_prefix="ctf",
        environment=HarborEnvironmentConfig(
            cpus=2.0,
            memory_mb=1024,
            storage_mb=10240,
            allow_internet=False,
            build_timeout_sec=600,
        ),
        author_name="Coding Task Factory",
        author_email="benchmark@codingtaskfactory.local",
    )


def export_sample_task(target_dir: Path) -> Path:
    """Exports and validates the deterministic sample task package."""
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = build_sample_task_payload()

    zip_path, report = export_harbor_task_package(payload, output_dir=target_dir)
    print(f"Exported ZIP archive: {zip_path} ({report.archive_size_bytes} bytes)")
    print(f"Harbor task name: {report.harbor_task_name}")

    # Extract to target directory for direct harbor lint / harbor run inspection
    extract_dest = target_dir
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Validate that no path traversal exists in archive
        for member in zf.namelist():
            if ".." in member or member.startswith("/"):
                raise ValueError(f"Unsafe path in ZIP archive: {member}")
        zf.extractall(extract_dest)

    task_folder = extract_dest / "ctf-sample-math-task"
    if not task_folder.exists():
        raise FileNotFoundError(f"Expected extracted directory not found: {task_folder}")

    # Verify all 5 essential Harbor assets are present
    required_assets = [
        task_folder / "task.toml",
        task_folder / "instruction.md",
        task_folder / "environment" / "Dockerfile",
        task_folder / "solution" / "solve.sh",
        task_folder / "tests" / "test.sh",
    ]

    for asset in required_assets:
        if not asset.exists():
            raise FileNotFoundError(f"Missing required Harbor asset: {asset}")
        if asset.stat().st_size == 0:
            raise ValueError(f"Required Harbor asset is empty: {asset}")

    print(f"Successfully generated and validated Harbor task directory: {task_folder}")
    print(f"Files exported ({len(report.files_exported)}): {', '.join(report.files_exported)}")
    return task_folder


def main():
    parser = argparse.ArgumentParser(description="Export deterministic sample Harbor task package.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="staged_harbor_task",
        help="Target directory where task directory and ZIP archive are placed",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir).resolve()
    task_dir = export_sample_task(out_path)
    print(f"TASK_DIRECTORY={task_dir}")


if __name__ == "__main__":
    main()
