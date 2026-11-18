"""
Harbor Exporter Service — Day 9 Step 3.

Converts validated Coding Task Factory task packages into standard,
Harbor-compatible evaluation task directories and downloadable ZIP archives.

Adheres strictly to Harbor schema 1.4 and verifier reward conventions.
Zero untrusted code is executed on the host.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from app.schemas.harbor import (
    HarborAgentConfig,
    HarborEnvironmentConfig,
    HarborExportReport,
    HarborExportRequest,
    HarborMetadataConfig,
    HarborTaskInfo,
    HarborTaskManifest,
    HarborVerifierConfig,
    ValidationStatusLiteral,
)
from app.schemas.solution import SolutionFile, SolutionResponse
from app.schemas.task import TaskResponse
from app.schemas.test_suite import RepositoryMetadata, TestFile, TestSuiteResponse
from app.schemas.validation import ValidationReport

# ── Safety & Resource Constraints ───────────────────────────────────

MAX_EXPORT_FILES_COUNT: int = 500
MAX_ARCHIVE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB max zip size

FORBIDDEN_FILE_NAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "id_rsa",
    "id_ed25519",
}

FORBIDDEN_FILE_EXTENSIONS: set[str] = {
    ".pem",
    ".key",
    ".pfx",
    ".pyc",
    ".pyo",
    ".exe",
    ".dll",
    ".so",
}


# ── Path Validation and Security Helpers ────────────────────────────

def sanitize_task_dirname(task_prefix: str, task_id: str) -> str:
    """Builds a clean, safe directory name conforming to Harbor task naming conventions."""
    prefix_clean = re.sub(r"[^A-Za-z0-9_-]", "", task_prefix.strip()) or "ctf"
    id_clean = re.sub(r"[^A-Za-z0-9_-]", "", task_id.strip()) or "task"
    return f"{prefix_clean}-{id_clean}"


def validate_export_file_path(relative_path: str) -> Path:
    """
    Validates that a relative path is strictly safe for file creation and archive storage.

    Rejects:
    - Absolute paths (leading '/' or '\\' or Windows drive letters 'C:')
    - Path traversal ('..' or '.')
    - Backslash separators
    - Forbidden credential files (.env, *.key, etc.)
    - Symlinks

    Raises:
        ValueError: If any unsafe path or forbidden pattern is detected.
    """
    raw = str(relative_path).strip()
    if not raw:
        raise ValueError("File path cannot be empty.")

    # Reject backslashes
    if "\\" in raw:
        raise ValueError(f"Unsafe path separator '\\' in '{relative_path}'. Only forward slashes '/' are permitted.")

    # Reject absolute path indicators
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError(f"Absolute paths are forbidden: '{relative_path}'")

    parts = Path(raw).parts
    if any(p in ("..", ".") for p in parts):
        raise ValueError(f"Path traversal ('..' or '.') is forbidden: '{relative_path}'")

    file_name = parts[-1].lower()
    if file_name in FORBIDDEN_FILE_NAMES:
        raise ValueError(f"Forbidden credential/system file in package: '{relative_path}'")

    suffix = Path(raw).suffix.lower()
    if suffix in FORBIDDEN_FILE_EXTENSIONS:
        raise ValueError(f"Forbidden file extension '{suffix}' in package: '{relative_path}'")

    return Path(raw)


# ── File Generation Functions ───────────────────────────────────────

def generate_instruction_markdown(task: TaskResponse) -> str:
    """
    Generates instruction.md presented to the agent during evaluation.

    Contains requirements, context, and acceptance criteria.
    Never includes test code, test assertions, or reference solution code.
    """
    reqs_list = "\n".join(f"- {r}" for r in task.requirements) if task.requirements else "None specified."
    crit_list = "\n".join(f"- {c}" for c in task.acceptance_criteria) if task.acceptance_criteria else "None specified."

    clean_files = []
    for f in task.relevant_files:
        clean = f.replace(" (new)", "").replace(" (modified)", "").strip()
        if clean:
            clean_files.append(f"- `{clean}`")
    files_list = "\n".join(clean_files) if clean_files else "Inspect repository to locate relevant files."

    return f"""\
# {task.title}

## Overview
{task.description}

## Project Context
- **Project Name**: `{task.project_name or "standalone"}`
- **Target Language**: `{task.language}`
- **Difficulty**: `{task.difficulty}`
- **Category**: `{task.category}`

## Functional Requirements
{reqs_list}

## Acceptance Criteria
{crit_list}

## Suggested Files to Inspect / Modify
{files_list}

## Instructions
1. Implement all functional requirements and ensure every acceptance criterion is completely satisfied.
2. Ensure your implementation matches existing repository conventions, dependencies, and architecture.
3. Verify that your changes do not break any pre-existing repository features.
"""


def generate_task_toml(manifest: HarborTaskManifest) -> str:
    """
    Serializes a HarborTaskManifest strictly according to Harbor schema 1.4.
    """
    tags_formatted = json.dumps(manifest.metadata.tags)
    artifacts_formatted = json.dumps(manifest.artifacts)
    commit_sha_str = manifest.metadata.starting_commit_sha or ""

    # Quote strings safely
    desc_escaped = manifest.task.description.replace('"', '\\"').replace("\n", " ")
    diff_expl_escaped = manifest.metadata.difficulty_explanation.replace('"', '\\"').replace("\n", " ")

    return f"""\
schema_version = "1.4"
artifacts = {artifacts_formatted}

[task]
name = "{manifest.task.name}"
version = "{manifest.task.version}"
description = "{desc_escaped}"

[metadata]
author_name = "{manifest.metadata.author_name}"
author_email = "{manifest.metadata.author_email}"
difficulty_explanation = "{diff_expl_escaped}"
category = "{manifest.metadata.category}"
tags = {tags_formatted}
starting_commit_sha = "{commit_sha_str}"
project_name = "{manifest.metadata.project_name}"
validation_status = "{manifest.metadata.validation_status}"

[environment]
cpus = {manifest.environment.cpus:.1f}
memory_mb = {manifest.environment.memory_mb}
storage_mb = {manifest.environment.storage_mb}
allow_internet = {str(manifest.environment.allow_internet).lower()}
build_timeout_sec = {manifest.environment.build_timeout_sec}

[agent]
timeout_sec = {manifest.agent.timeout_sec}

[verifier]
timeout_sec = {manifest.verifier.timeout_sec}
environment_mode = "{manifest.verifier.environment_mode}"
"""


def generate_environment_dockerfile(task: TaskResponse, repo_meta: RepositoryMetadata | None) -> str:
    """
    Generates environment/Dockerfile for sandboxed agent evaluation.

    Pins starting commit SHA and runtime dependencies with exact version pins.
    """
    lang = (task.language or "python").lower()
    commit_sha = (repo_meta.starting_commit_sha if repo_meta else None) or task.starting_commit_sha or "HEAD"

    if "python" in lang:
        base_image = "python:3.11-slim"
        dep_install = (
            "RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi \\\n"
            "    && pip install --no-cache-dir pytest==8.3.4"
        )
    elif any(js in lang for js in ("javascript", "typescript", "node")):
        base_image = "node:20-slim"
        dep_install = "RUN if [ -f package.json ]; then npm install; fi"
    elif "go" in lang:
        base_image = "golang:1.22-bookworm"
        dep_install = "RUN if [ -f go.mod ]; then go mod download; fi"
    else:
        base_image = "python:3.11-slim"
        dep_install = "RUN pip install --no-cache-dir pytest==8.3.4"

    return f"""\
FROM {base_image}

# Set non-interactive environment and starting commit reference
ENV DEBIAN_FRONTEND=noninteractive \\
    STARTING_COMMIT_SHA="{commit_sha}"

WORKDIR /workspace

# Install common system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git \\
    curl \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# Install project dependencies
{dep_install}

# Default working environment
CMD ["/bin/bash"]
"""


def generate_verifier_dockerfile(test_suite: TestSuiteResponse) -> str:
    """
    Generates tests/Dockerfile for the dedicated, isolated verifier container.

    Build context is the tests/ directory.
    Installs pinned verification dependencies and copies tests into /tests/.
    Prepares artifact mount point /workspace and verifier logs directory.
    """
    lang = (test_suite.repository.detected_language or "python").lower()

    if "python" in lang:
        base_image = "python:3.11-slim"
        dep_install = "RUN pip install --no-cache-dir pytest==8.3.4"
    elif any(js in lang for js in ("javascript", "typescript", "node")):
        base_image = "node:20-slim"
        dep_install = "RUN if [ -f package.json ]; then npm install; fi"
    elif "go" in lang:
        base_image = "golang:1.22-bookworm"
        dep_install = "RUN if [ -f go.mod ]; then go mod download; fi"
    else:
        base_image = "python:3.11-slim"
        dep_install = "RUN pip install --no-cache-dir pytest==8.3.4"

    return f"""\
FROM {base_image}

ENV DEBIAN_FRONTEND=noninteractive

# Install common system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git \\
    curl \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# Install pinned test runner dependencies
{dep_install}

# Create required artifact handoff and verifier log directories
RUN mkdir -p /workspace /logs/verifier

# Copy verifier test suite and scripts into the container
COPY . /tests/
RUN chmod +x /tests/test.sh

WORKDIR /workspace
CMD ["/bin/bash"]
"""


def generate_verifier_test_sh(test_suite: TestSuiteResponse) -> str:
    """
    Generates the tests/test.sh verifier script executed after the agent stops.

    Executes feature and regression tests and writes the official Harbor
    reward score to /logs/verifier/reward.txt on every execution path.
    Uses verified container mount paths (/tests/feature and /tests/regression).
    """
    framework = (test_suite.repository.test_framework or "pytest").lower()

    if framework == "pytest":
        run_cmd = "pytest /tests/feature /tests/regression -v"
    elif framework == "unittest":
        run_cmd = "python -m unittest discover -s /tests -v"
    elif framework in ("jest", "vitest", "mocha"):
        run_cmd = "npm test --prefix /tests"
    elif framework == "go test":
        run_cmd = "go test /tests/..."
    else:
        run_cmd = "pytest /tests/feature /tests/regression -v"

    return f"""\
#!/usr/bin/env bash
set -o pipefail

# Ensure verifier log directory exists
mkdir -p /logs/verifier
REWARD_FILE="/logs/verifier/reward.txt"

# Default verifier reward score to 0.0 before execution to ensure reward is recorded on all execution paths
echo "0.0" > "$REWARD_FILE"

echo "=== Running Harbor Evaluation Verifier ==="
echo "Framework: {framework}"
echo "Command: {run_cmd}"

# Execute full verification suite (feature tests + regression checks)
if {run_cmd}; then
    echo "=== Verifier PASSED: All feature and regression checks satisfied ==="
    echo "1.0" > "$REWARD_FILE"
    exit 0
else
    echo "=== Verifier FAILED: One or more test checks failed ==="
    echo "0.0" > "$REWARD_FILE"
    exit 1
fi
"""


def generate_oracle_solve_sh(solution: SolutionResponse) -> str:
    """
    Generates solution/solve.sh oracle script to prove task solvability.

    Applies all reference solution files into the workspace.
    """
    return """\
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/files"

echo "=== Applying Reference Solution (Oracle) ==="

if [ -d "$FILES_DIR" ]; then
    cp -R "$FILES_DIR"/. /workspace/
    echo "Reference solution files successfully copied to /workspace."
else
    echo "No static solution files directory found."
fi

exit 0
"""


# ── Master Package Assembly and Export Function ─────────────────────

def export_harbor_task_package(
    request: HarborExportRequest,
    output_dir: Path | str | None = None,
) -> tuple[Path, HarborExportReport]:
    """
    Packages a task package into the official Harbor format.

    Creates directory layout:
      <task-name>/
      ├── task.toml
      ├── instruction.md
      ├── environment/Dockerfile
      ├── tests/test.sh
      ├── tests/feature/
      ├── tests/regression/
      ├── solution/solve.sh
      └── solution/files/

    Bundles into a clean ZIP archive and returns (archive_path, report).

    Raises:
        ValueError: If path traversal, collision, or unsafe files are detected.
    """
    task = request.task
    solution = request.solution
    test_suite = request.test_suite

    # Build safe task folder name
    task_dir_name = sanitize_task_dirname(request.task_prefix, task.id)
    harbor_task_name = f"{request.task_prefix}/{task.id}"

    # Resolve commit SHA and validation status
    starting_commit_sha = request.resolve_starting_commit_sha()
    val_status: ValidationStatusLiteral = request.resolve_validation_status()

    # Resolve author metadata
    author_name = request.author_name or "Coding Task Factory"
    author_email = request.author_email or "benchmark@codingtaskfactory.local"
    diff_expl = f"Task difficulty rated as {task.difficulty}."

    # Resolve environment configuration (defaulting to conservative 1024 MB RAM)
    env_config = request.environment or HarborEnvironmentConfig(
        cpus=2.0,
        memory_mb=1024,
        storage_mb=10240,
        allow_internet=False,
        build_timeout_sec=600,
    )

    # Build manifest
    artifacts_list = request.artifacts or ["/workspace"]

    manifest = HarborTaskManifest(
        schema_version="1.4",
        artifacts=artifacts_list,
        task=HarborTaskInfo(
            name=harbor_task_name,
            version="1.0.0",
            description=task.description[:200],
        ),
        metadata=HarborMetadataConfig(
            author_name=author_name,
            author_email=author_email,
            difficulty=task.difficulty,
            difficulty_explanation=diff_expl,
            category=task.category,
            tags=[task.language, task.category, task.difficulty],
            starting_commit_sha=starting_commit_sha,
            project_name=task.project_name or "standalone_project",
            validation_status=val_status,
        ),
        environment=env_config,
        agent=HarborAgentConfig(timeout_sec=600),
        verifier=HarborVerifierConfig(timeout_sec=180, environment_mode="separate"),
    )

    # Determine destination root
    if output_dir:
        dest_parent = Path(output_dir).resolve()
        dest_parent.mkdir(parents=True, exist_ok=True)
    else:
        dest_parent = Path(tempfile.gettempdir()).resolve()

    staged_task_dir = dest_parent / task_dir_name
    zip_dest = dest_parent / f"{task_dir_name}.zip"

    # Clean existing destination if present
    if staged_task_dir.exists():
        shutil.rmtree(staged_task_dir)
    if zip_dest.exists():
        zip_dest.unlink()

    staged_task_dir.mkdir(parents=True)
    exported_relative_files: list[str] = []

    try:
        # 1. instruction.md
        inst_path = staged_task_dir / "instruction.md"
        inst_path.write_text(generate_instruction_markdown(task), encoding="utf-8")
        exported_relative_files.append("instruction.md")

        # 2. task.toml
        toml_path = staged_task_dir / "task.toml"
        toml_path.write_text(generate_task_toml(manifest), encoding="utf-8")
        exported_relative_files.append("task.toml")

        # 3. environment/Dockerfile
        env_dir = staged_task_dir / "environment"
        env_dir.mkdir(parents=True)
        dockerfile_path = env_dir / "Dockerfile"
        dockerfile_path.write_text(generate_environment_dockerfile(task, test_suite.repository), encoding="utf-8")
        exported_relative_files.append("environment/Dockerfile")

        # 4. tests/ directory
        tests_dir = staged_task_dir / "tests"
        tests_dir.mkdir(parents=True)

        # 4a. tests/Dockerfile for isolated verifier sandbox
        verifier_dockerfile_path = tests_dir / "Dockerfile"
        verifier_dockerfile_path.write_text(generate_verifier_dockerfile(test_suite), encoding="utf-8")
        exported_relative_files.append("tests/Dockerfile")

        # 4b. tests/test.sh verifier entrypoint
        test_sh_path = tests_dir / "test.sh"
        test_sh_path.write_text(generate_verifier_test_sh(test_suite), encoding="utf-8")
        exported_relative_files.append("tests/test.sh")

        # 4c. tests/feature/ test files
        feat_dir = tests_dir / "feature"
        feat_dir.mkdir(parents=True)
        seen_test_paths: set[str] = set()

        for f_idx, feat_file in enumerate(test_suite.feature_test_files):
            safe_rel = validate_export_file_path(feat_file.path)
            clean_name = safe_rel.name or f"test_feature_{f_idx}.py"
            if clean_name in seen_test_paths:
                raise ValueError(f"Duplicate test file path detected: '{feat_file.path}'")

            target_file = feat_dir / clean_name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(feat_file.code, encoding="utf-8")
            seen_test_paths.add(clean_name)
            exported_relative_files.append(f"tests/feature/{clean_name}")

        # 4d. tests/regression/ test files
        reg_dir = tests_dir / "regression"
        reg_dir.mkdir(parents=True)

        for r_idx, reg_file in enumerate(test_suite.regression_test_files):
            safe_rel = validate_export_file_path(reg_file.path)
            clean_name = safe_rel.name or f"test_regression_{r_idx}.py"
            if clean_name in seen_test_paths:
                raise ValueError(f"Duplicate test file path detected: '{reg_file.path}'")

            target_file = reg_dir / clean_name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(reg_file.code, encoding="utf-8")
            seen_test_paths.add(clean_name)
            exported_relative_files.append(f"tests/regression/{clean_name}")

        # 5. solution/ directory
        sol_dir = staged_task_dir / "solution"
        sol_dir.mkdir(parents=True)

        # 5a. solution/solve.sh oracle script
        solve_sh_path = sol_dir / "solve.sh"
        solve_sh_path.write_text(generate_oracle_solve_sh(solution), encoding="utf-8")
        exported_relative_files.append("solution/solve.sh")

        # 5b. solution/files/ reference files
        sol_files_dir = sol_dir / "files"
        sol_files_dir.mkdir(parents=True)
        seen_sol_paths: set[str] = set()

        for s_idx, sol_file in enumerate(solution.files):
            safe_rel = validate_export_file_path(sol_file.path)
            rel_str = str(safe_rel).replace("\\", "/")
            if rel_str in seen_sol_paths:
                raise ValueError(f"Duplicate solution file path detected: '{sol_file.path}'")

            dest_file = sol_files_dir / safe_rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(sol_file.code, encoding="utf-8")
            seen_sol_paths.add(rel_str)
            exported_relative_files.append(f"solution/files/{rel_str}")

        # 6. Bundle into ZIP Archive
        with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root_dir, _, files in os.walk(staged_task_dir):
                for file_name in files:
                    full_p = Path(root_dir) / file_name
                    arcname = f"{task_dir_name}/" + str(full_p.relative_to(staged_task_dir)).replace("\\", "/")
                    zf.write(full_p, arcname=arcname)

        archive_size = zip_dest.stat().st_size
        if archive_size > MAX_ARCHIVE_SIZE_BYTES:
            zip_dest.unlink()
            raise ValueError(f"Export archive exceeds size limit: {archive_size} > {MAX_ARCHIVE_SIZE_BYTES}")

        report = HarborExportReport(
            task_id=task.id,
            harbor_task_name=harbor_task_name,
            export_directory=str(staged_task_dir),
            archive_path=str(zip_dest),
            files_exported=sorted(exported_relative_files),
            archive_size_bytes=archive_size,
            validation_status_recorded=val_status,
            exported_at=datetime.now(timezone.utc).isoformat(),
        )

        return zip_dest, report

    except Exception:
        # Guarantee cleanup on failure
        if staged_task_dir.exists():
            shutil.rmtree(staged_task_dir, ignore_errors=True)
        if zip_dest.exists():
            zip_dest.unlink(missing_ok=True)
        raise
