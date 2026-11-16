"""
Repository Scanner & Ingestion Service.

Provides:
- SSRF-protected GitHub repository archive downloading.
- Hardened ZIP archive validation & extraction.
- Recursive, safe static scanning of codebases (no code execution).
"""

import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlsplit

import requests

from app.schemas.repo import RepoAnalysisResponse

# ── Security & Limits Constants ─────────────────────────────────────

MAX_ZIP_SIZE_BYTES: int = 25 * 1024 * 1024       # 25 MB max upload/download
MAX_EXTRACTED_SIZE_BYTES: int = 100 * 1024 * 1024 # 100 MB max uncompressed bytes
MAX_EXTRACTED_FILE_COUNT: int = 1500              # Max files in archive
MAX_SINGLE_FILE_SIZE_BYTES: int = 10 * 1024 * 1024 # 10 MB per individual file
MAX_COMPRESSION_RATIO: float = 20.0               # Max ratio uncompressed:compressed
CHUNK_SIZE: int = 64 * 1024                       # 64 KB read buffer

NETWORK_CONNECT_TIMEOUT_SEC: float = 5.0
NETWORK_READ_TIMEOUT_SEC: float = 30.0
MAX_REDIRECT_HOPS: int = 3

ALLOWED_GITHUB_HOSTS: set[str] = {"github.com", "codeload.github.com"}

IGNORED_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    "target",
    "bin",
    "obj",
}

IGNORED_EXTENSIONS: set[str] = {
    # Binaries & executables
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".pyc", ".pyo", ".class",
    # Archives & bundles
    ".zip", ".tar", ".gz", ".7z", ".rar", ".jar", ".war",
    # Media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".mp3", ".mp4", ".wav", ".avi",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Documents
    ".pdf", ".docx", ".xlsx", ".pptx",
    # DB & data dumps
    ".db", ".sqlite", ".sqlite3", ".parquet",
}

MAX_FILES_TO_SCAN: int = 1000
MAX_FILE_SIZE_BYTES: int = 500 * 1024  # 500 KB limit per file inspected
MAX_README_CHARS: int = 2000

# ── Extension to Language Mapping ───────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
}

PYTHON_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "tortoise-orm": "Tortoise ORM",
    "celery": "Celery",
    "pytest": "Pytest",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "tensorflow": "TensorFlow",
    "torch": "PyTorch",
    "google-genai": "Google GenAI",
    "openai": "OpenAI SDK",
}

JS_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue.js",
    "nuxt": "Nuxt.js",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "tailwindcss": "Tailwind CSS",
    "prisma": "Prisma",
    "mongoose": "Mongoose",
}

JAVA_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "spring-boot": "Spring Boot",
    "spring-web": "Spring MVC",
    "hibernate": "Hibernate",
    "quarkus": "Quarkus",
}

GO_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "github.com/gin-gonic/gin": "Gin",
    "github.com/labstack/echo": "Echo",
    "github.com/gofiber/fiber": "Fiber",
    "gorm.io/gorm": "GORM",
}


# ── SSRF & Network Security ─────────────────────────────────────────

def _is_ip_safe(ip_str: str) -> bool:
    """Verify that an IP address is not private, loopback, link-local, reserved or multicast."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
        return True
    except ValueError:
        return False


def _verify_hostname_and_dns(hostname: str) -> None:
    """Validate that hostname belongs to allowed hosts and resolves only to public IPs."""
    host_lower = hostname.lower()
    if host_lower not in ALLOWED_GITHUB_HOSTS:
        raise ValueError(
            f"Host '{hostname}' is not a trusted GitHub domain. Allowed: {ALLOWED_GITHUB_HOSTS}"
        )

    # Perform DNS resolution check
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for '{hostname}': {exc}") from exc

    for entry in addr_info:
        sock_addr = entry[4]
        ip_str = sock_addr[0]
        if not _is_ip_safe(ip_str):
            raise ValueError(
                f"Security violation: Host '{hostname}' resolved to disallowed/private IP '{ip_str}'"
            )


def parse_and_validate_github_url(repo_url: str) -> tuple[str, str]:
    """
    Validate GitHub repository URL and return (owner, repo).
    Enforces HTTPS, github.com host, no credentials, and owner/repo pattern.
    """
    parts = urlsplit(repo_url)

    if parts.scheme.lower() != "https":
        raise ValueError("Only HTTPS repository URLs are allowed.")

    if parts.username or parts.password:
        raise ValueError("URL credentials are not permitted.")

    hostname = (parts.hostname or "").lower()
    if hostname != "github.com":
        raise ValueError(f"Invalid host '{hostname}'. Expected 'github.com'.")

    if parts.port and parts.port != 443:
        raise ValueError("Only default HTTPS port (443) is permitted.")

    # Match /owner/repo or /owner/repo.git
    path = parts.path.strip("/")
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?", path)
    if not match:
        raise ValueError(
            f"Invalid GitHub repository path: '{parts.path}'. Expected format: '/owner/repo'."
        )

    owner, repo = match.group(1), match.group(2)
    # Reject directory traversal attempts in repo or owner name
    if owner in (".", "..") or repo in (".", ".."):
        raise ValueError("Invalid owner or repository name.")

    return owner, repo


def download_github_archive(owner: str, repo: str, destination_file: Path) -> None:
    """
    Safely download GitHub repository archive HEAD.zip using manual redirect handling
    and DNS/IP re-verification at every hop.
    """
    current_url = f"https://github.com/{owner}/{repo}/archive/HEAD.zip"
    total_downloaded = 0

    session = requests.Session()

    for hop in range(MAX_REDIRECT_HOPS + 1):
        parts = urlsplit(current_url)
        hostname = parts.hostname or ""

        # Validate host and verify resolved IP on each hop
        _verify_hostname_and_dns(hostname)

        try:
            with session.get(
                current_url,
                stream=True,
                allow_redirects=False,
                timeout=(NETWORK_CONNECT_TIMEOUT_SEC, NETWORK_READ_TIMEOUT_SEC),
                headers={"User-Agent": "CodingTaskFactory-Bot/1.0"},
            ) as response:

                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect response missing Location header.")
                    # Handle relative vs absolute redirect URLs
                    if location.startswith("/"):
                        current_url = f"https://{hostname}{location}"
                    else:
                        current_url = location
                    continue

                if response.status_code == 404:
                    raise FileNotFoundError(
                        f"GitHub repository '{owner}/{repo}' was not found or is private."
                    )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"GitHub returned HTTP status {response.status_code} while downloading archive."
                    )

                # Stream response content into destination file
                with open(destination_file, "wb") as f_out:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            total_downloaded += len(chunk)
                            if total_downloaded > MAX_ZIP_SIZE_BYTES:
                                raise ValueError(
                                    f"Repository archive exceeds maximum allowed size of {MAX_ZIP_SIZE_BYTES // (1024 * 1024)} MB."
                                )
                            f_out.write(chunk)
                return

        except (requests.ConnectionError, requests.Timeout) as exc:
            raise RuntimeError(f"Network error downloading repository archive: {exc}") from exc

    raise ValueError(f"Exceeded maximum allowed redirect hops ({MAX_REDIRECT_HOPS}).")


# ── Hardened ZIP Extraction ─────────────────────────────────────────

def safe_extract_zip(zip_path: Path, extract_dir: Path) -> Path:
    """
    Validates and securely extracts a ZIP archive into extract_dir.

    Enforces:
    - Magic bytes header check
    - Structural integrity check via zipfile.is_zipfile and testzip
    - Rejection of encrypted archives
    - Rejection of symbolic links
    - Rejection of path traversal (Zip Slip), absolute paths, and Windows drive/backslash patterns
    - Total extracted size, single file size, file count, and compression ratio limits
    """
    extract_dir = extract_dir.resolve()

    if not zip_path.exists() or zip_path.stat().st_size == 0:
        raise ValueError("ZIP archive is empty or missing.")

    if zip_path.stat().st_size > MAX_ZIP_SIZE_BYTES:
        raise ValueError(
            f"Archive file exceeds limit of {MAX_ZIP_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # Magic byte signature check
    with open(zip_path, "rb") as f:
        header = f.read(4)
        if header not in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
            raise ValueError("File does not have a valid ZIP magic byte header.")

    if not zipfile.is_zipfile(zip_path):
        raise ValueError("File is not a valid or readable ZIP archive.")

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            entries = archive.infolist()
            if len(entries) > MAX_EXTRACTED_FILE_COUNT:
                raise ValueError(
                    f"ZIP archive contains {len(entries)} files, exceeding limit of {MAX_EXTRACTED_FILE_COUNT}."
                )

            # Check for encrypted entries before testing or extracting
            for info in entries:
                if info.flag_bits & 0x1:
                    raise ValueError(f"Encrypted ZIP entries are not permitted: '{info.filename}'.")

            # Check for corrupted files
            try:
                bad_file = archive.testzip()
                if bad_file:
                    raise ValueError(f"Corrupted entry detected in ZIP archive: '{bad_file}'.")
            except RuntimeError as exc:
                if "encrypted" in str(exc).lower():
                    raise ValueError(f"Encrypted ZIP entries are not permitted: {exc}") from exc
                raise ValueError(f"Corrupted entry detected in ZIP archive: {exc}") from exc

            total_uncompressed_size = 0

            # Pre-validation pass over all members
            for info in entries:
                filename = info.filename

                # Reject encrypted entries
                if info.flag_bits & 0x1:
                    raise ValueError(f"Encrypted ZIP entries are not permitted: '{filename}'.")

                # Reject symbolic links (POSIX mode in external_attr)
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ValueError(f"Symbolic links in ZIP archives are forbidden: '{filename}'.")

                # Reject absolute or Windows drive paths
                if filename.startswith("/") or filename.startswith("\\"):
                    raise ValueError(f"Absolute path in archive forbidden: '{filename}'.")
                if re.match(r"^[A-Za-z]:", filename):
                    raise ValueError(f"Windows drive path in archive forbidden: '{filename}'.")
                if "\\" in filename:
                    # Windows backslash traversal
                    cleaned_name = filename.replace("\\", "/")
                else:
                    cleaned_name = filename

                # Reject relative traversal segments (..)
                parts = Path(cleaned_name).parts
                if ".." in parts:
                    raise ValueError(f"Directory traversal detected in archive path: '{filename}'.")

                # Size and ratio checks
                if info.file_size > MAX_SINGLE_FILE_SIZE_BYTES:
                    raise ValueError(
                        f"Single file '{filename}' exceeds {MAX_SINGLE_FILE_SIZE_BYTES // (1024 * 1024)} MB limit."
                    )

                total_uncompressed_size += info.file_size
                if total_uncompressed_size > MAX_EXTRACTED_SIZE_BYTES:
                    raise ValueError(
                        f"Extracted archive size exceeds {MAX_EXTRACTED_SIZE_BYTES // (1024 * 1024)} MB limit."
                    )

                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > MAX_COMPRESSION_RATIO and info.file_size > 50 * 1024:
                        raise ValueError(
                            f"Suspicious compression ratio ({ratio:.1f}:1) detected for '{filename}' (potential Zip Bomb)."
                        )

            # Extraction pass
            for info in entries:
                clean_name = info.filename.replace("\\", "/")
                target_path = (extract_dir / clean_name).resolve()

                # Zip Slip strict assertion
                if not target_path.is_relative_to(extract_dir):
                    raise ValueError(f"Path traversal detected: '{info.filename}'.")

                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source_f, open(target_path, "wb") as dest_f:
                        shutil.copyfileobj(source_f, dest_f)

    except zipfile.BadZipFile as exc:
        raise ValueError(f"Malformed or unreadable ZIP archive: {exc}") from exc

    # If the ZIP unpacked into a single top-level folder (e.g. GitHub archive root),
    # return that folder as the root for scanning.
    top_entries = list(extract_dir.iterdir())
    if len(top_entries) == 1 and top_entries[0].is_dir():
        return top_entries[0]

    return extract_dir


def stream_upload_to_disk(upload_stream: BinaryIO, destination: Path) -> int:
    """Stream incoming upload file in chunks to disk, checking size limit on the fly."""
    total_bytes = 0
    with open(destination, "wb") as out_f:
        while True:
            chunk = upload_stream.read(CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_ZIP_SIZE_BYTES:
                raise ValueError(
                    f"Uploaded file exceeds maximum limit of {MAX_ZIP_SIZE_BYTES // (1024 * 1024)} MB."
                )
            out_f.write(chunk)
    return total_bytes


# ── Repository Analysis Functions ───────────────────────────────────

def analyze_github_repository(repo_url: str) -> RepoAnalysisResponse:
    """Download, safely unpack, and analyze a public GitHub repository."""
    owner, repo = parse_and_validate_github_url(repo_url)

    with tempfile.TemporaryDirectory(prefix="ctf_github_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        zip_file = temp_dir / "repo.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()

        # Step 1: Download
        download_github_archive(owner, repo, zip_file)

        # Step 2: Extract safely
        source_root = safe_extract_zip(zip_file, extract_dir)

        # Step 3: Scan codebase
        analysis = scan_local_repository(
            repo_path=source_root,
            project_name=repo,
            source_type="github",
        )
        return analysis


def analyze_uploaded_zip(file_stream: BinaryIO, filename: str) -> RepoAnalysisResponse:
    """Stream, safely unpack, and analyze an uploaded ZIP file."""
    base_name = Path(filename).stem or "uploaded_project"

    with tempfile.TemporaryDirectory(prefix="ctf_upload_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        zip_file = temp_dir / "upload.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()

        # Step 1: Stream to disk
        stream_upload_to_disk(file_stream, zip_file)

        # Step 2: Extract safely
        source_root = safe_extract_zip(zip_file, extract_dir)

        # Step 3: Scan codebase
        analysis = scan_local_repository(
            repo_path=source_root,
            project_name=base_name,
            source_type="zip",
        )
        return analysis


# ── Local Repository Scanner ────────────────────────────────────────

def _safe_read_text(file_path: Path, max_chars: int | None = None) -> str:
    """Read text from file safely with size and encoding fallback."""
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
            return ""
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if max_chars and len(content) > max_chars:
            return content[:max_chars].strip() + "\n...(truncated)"
        return content
    except Exception:
        return ""


def _extract_frameworks_from_python_config(content: str) -> set[str]:
    detected = set()
    lower = content.lower()
    for signature, framework_name in PYTHON_FRAMEWORK_SIGNATURES.items():
        if signature in lower:
            detected.add(framework_name)
    return detected


def _extract_frameworks_from_package_json(content: str) -> set[str]:
    detected = set()
    try:
        data = json.loads(content)
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        deps_keys = {k.lower() for k in deps.keys()}
        for signature, framework_name in JS_FRAMEWORK_SIGNATURES.items():
            if signature.lower() in deps_keys:
                detected.add(framework_name)
    except Exception:
        pass
    return detected


def _extract_frameworks_from_pom_xml(content: str) -> set[str]:
    detected = set()
    lower = content.lower()
    for signature, framework_name in JAVA_FRAMEWORK_SIGNATURES.items():
        if signature in lower:
            detected.add(framework_name)
    return detected


def _extract_frameworks_from_go_mod(content: str) -> set[str]:
    detected = set()
    for signature, framework_name in GO_FRAMEWORK_SIGNATURES.items():
        if signature in content:
            detected.add(framework_name)
    return detected


def scan_local_repository(
    repo_path: str | Path,
    project_name: str | None = None,
    source_type: Literal["github", "zip"] = "zip",
) -> RepoAnalysisResponse:
    """Recursively inspects a local repository path and returns a structured RepoAnalysisResponse."""
    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository path does not exist or is not a directory: {repo_path}")

    actual_project_name = project_name or root.name

    language_counts: dict[str, int] = {}
    detected_frameworks: set[str] = set()
    folders: set[str] = set()
    readme_content: str | None = None
    scanned_file_count = 0

    for item in root.rglob("*"):
        if scanned_file_count >= MAX_FILES_TO_SCAN:
            break

        try:
            rel_parts = item.relative_to(root).parts
        except ValueError:
            continue

        if any(part in IGNORED_DIRS for part in rel_parts):
            continue

        if item.is_dir():
            if len(rel_parts) <= 2:
                folders.add("/".join(rel_parts))
            continue

        if not item.is_file():
            continue

        suffix = item.suffix.lower()
        if suffix in IGNORED_EXTENSIONS:
            continue

        scanned_file_count += 1
        name_lower = item.name.lower()

        if name_lower in ("readme.md", "readme.txt", "readme"):
            if readme_content is None:
                readme_content = _safe_read_text(item, max_chars=MAX_README_CHARS)

        if suffix in EXTENSION_TO_LANGUAGE:
            lang = EXTENSION_TO_LANGUAGE[suffix]
            language_counts[lang] = language_counts.get(lang, 0) + 1

        if name_lower in ("requirements.txt", "pyproject.toml", "pipfile"):
            content = _safe_read_text(item)
            detected_frameworks.update(_extract_frameworks_from_python_config(content))

        elif name_lower == "package.json":
            content = _safe_read_text(item)
            detected_frameworks.update(_extract_frameworks_from_package_json(content))

        elif name_lower == "pom.xml":
            content = _safe_read_text(item)
            detected_frameworks.update(_extract_frameworks_from_pom_xml(content))

        elif name_lower == "go.mod":
            content = _safe_read_text(item)
            detected_frameworks.update(_extract_frameworks_from_go_mod(content))

    sorted_languages = [
        lang for lang, _ in sorted(language_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    sorted_frameworks = sorted(detected_frameworks)
    sorted_folders = sorted(folders)

    return RepoAnalysisResponse(
        project_name=actual_project_name,
        source_type=source_type,
        detected_languages=sorted_languages,
        detected_frameworks=sorted_frameworks,
        file_count=scanned_file_count,
        folder_structure=sorted_folders,
        readme_summary=readme_content,
        analysis_status="completed",
    )


# ── Test Framework & Existing Test Detection ───────────────────────

TEST_CONFIG_FILENAMES: dict[str, str] = {
    "pytest.ini": "pytest",
    ".pytest.ini": "pytest",
    "jest.config.js": "jest",
    "jest.config.ts": "jest",
    "jest.config.mjs": "jest",
    "jest.config.json": "jest",
    "vitest.config.ts": "vitest",
    "vitest.config.js": "vitest",
    "vitest.config.mjs": "vitest",
    ".mocharc.json": "mocha",
    ".mocharc.js": "mocha",
    ".mocharc.yml": "mocha",
    ".mocharc.yaml": "mocha",
}


def _is_test_file(rel_path: str, filename_lower: str, suffix: str) -> bool:
    """Check whether a file matches conventional test naming conventions."""
    parts_lower = [p.lower() for p in rel_path.split("/")]

    # Check directory name hints
    in_test_dir = any(d in parts_lower[:-1] for d in ("tests", "test", "__tests__", "spec", "specs"))

    if suffix == ".py":
        return filename_lower.startswith("test_") or filename_lower.endswith("_test.py") or (in_test_dir and suffix == ".py")

    if suffix in (".js", ".jsx", ".ts", ".tsx"):
        return (
            ".test." in filename_lower
            or ".spec." in filename_lower
            or (in_test_dir and suffix in (".js", ".jsx", ".ts", ".tsx"))
        )

    if suffix == ".go":
        return filename_lower.endswith("_test.go")

    return False


def detect_test_framework_and_files(repo_path: str | Path) -> dict:
    """
    Statically inspects a repository to detect its active test framework,
    relevant test configuration files, and existing test files.

    Never executes repository code.

    Returns:
        dict with keys:
            - test_framework: str (e.g. 'pytest', 'unittest', 'jest', 'vitest', 'mocha', 'go test', 'unknown')
            - test_framework_config_file: str | None (relative path to detected config file)
            - existing_test_files: list[str] (relative paths to pre-existing test files, sorted)
    """
    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository path does not exist or is not a directory: {repo_path}")

    detected_framework: str = "unknown"
    detected_config_file: str | None = None
    existing_test_files: set[str] = set()

    found_configs: list[tuple[str, str]] = []  # (framework, rel_path)
    file_inspect_frameworks: list[str] = []

    scanned_count = 0

    for item in root.rglob("*"):
        if scanned_count >= MAX_FILES_TO_SCAN:
            break

        try:
            rel_parts = item.relative_to(root).parts
        except ValueError:
            continue

        if any(part in IGNORED_DIRS for part in rel_parts):
            continue

        if not item.is_file():
            continue

        suffix = item.suffix.lower()
        if suffix in IGNORED_EXTENSIONS:
            continue

        scanned_count += 1
        name_lower = item.name.lower()
        rel_str = "/".join(rel_parts)

        # 1. Identify test files
        if _is_test_file(rel_str, name_lower, suffix):
            existing_test_files.add(rel_str)
            # Lightweight content check for test framework signature if safe size
            if suffix == ".py" and detected_framework == "unknown":
                content_sample = _safe_read_text(item, max_chars=1000).lower()
                if "import pytest" in content_sample or "from pytest" in content_sample:
                    file_inspect_frameworks.append("pytest")
                elif "import unittest" in content_sample or "unittest.testcase" in content_sample:
                    file_inspect_frameworks.append("unittest")
            elif suffix == ".go":
                file_inspect_frameworks.append("go test")

        # 2. Check dedicated test config filenames
        if name_lower in TEST_CONFIG_FILENAMES:
            framework = TEST_CONFIG_FILENAMES[name_lower]
            found_configs.append((framework, rel_str))

        # 3. Check multi-purpose config files for test sections
        elif name_lower == "package.json":
            content = _safe_read_text(item)
            try:
                pkg_data = json.loads(content)
                all_deps = {
                    **pkg_data.get("dependencies", {}),
                    **pkg_data.get("devDependencies", {}),
                }
                deps_lower = {k.lower() for k in all_deps.keys()}
                test_script = str(pkg_data.get("scripts", {}).get("test", "")).lower()

                # Prioritize explicit dependencies, or test script containing the exact runner command
                if "vitest" in deps_lower or re.search(r"\bvitest\b", test_script):
                    found_configs.append(("vitest", rel_str))
                elif "jest" in deps_lower or re.search(r"\bjest\b", test_script):
                    found_configs.append(("jest", rel_str))
                elif "mocha" in deps_lower or re.search(r"\bmocha\b", test_script):
                    found_configs.append(("mocha", rel_str))
            except Exception:
                pass

        elif name_lower in ("pyproject.toml", "setup.cfg"):
            content = _safe_read_text(item).lower()
            if (
                "[tool.pytest.ini_options]" in content
                or "[tool.pytest]" in content
                or "[tool:pytest]" in content
                or "[pytest]" in content
                or "pytest" in content
            ):
                found_configs.append(("pytest", rel_str))

        elif name_lower in ("requirements.txt", "pipfile"):
            content = _safe_read_text(item).lower()
            if "pytest" in content:
                found_configs.append(("pytest", rel_str))

    # Priority 1: Dedicated or declared configuration file
    if found_configs:
        detected_framework, detected_config_file = found_configs[0]
    # Priority 2: Framework inferred from test file contents
    elif file_inspect_frameworks:
        # Pick the most frequent or first
        detected_framework = file_inspect_frameworks[0]
    # Priority 3: Fallback if test files exist but no framework declared
    elif existing_test_files:
        has_py = any(f.endswith(".py") for f in existing_test_files)
        has_js = any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in existing_test_files)
        has_go = any(f.endswith(".go") for f in existing_test_files)
        if has_py:
            detected_framework = "pytest"
        elif has_js:
            detected_framework = "jest"
        elif has_go:
            detected_framework = "go test"

    return {
        "test_framework": detected_framework,
        "test_framework_config_file": detected_config_file,
        "existing_test_files": sorted(existing_test_files),
    }
