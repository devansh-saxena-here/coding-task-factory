from pathlib import Path
import tempfile
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.schemas.harbor import HarborExportRequest
from app.schemas.repo import RepoAnalysisRequest, RepoAnalysisResponse
from app.schemas.solution import SolutionRequest, SolutionResponse
from app.schemas.task import (
    GenerateFromGithubRequest,
    GenerateFromRepoRequest,
    RepoTaskRequest,
    TaskRequest,
    TaskResponse,
)
from app.schemas.test_suite import TestSuiteRequest, TestSuiteResponse
from app.schemas.validation import ValidationReport, ValidationRequest
from app.services import (
    harbor_service,
    repo_service,
    solution_service,
    task_service,
    test_service,
    validation_service,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ── Topic-based Task Endpoints ──────────────────────────────────────

@router.get("/")
def list_tasks():
    """List all generated tasks (placeholder — database coming in a future phase)."""
    return {"tasks": [], "message": "Task listing will be available in a future phase."}


@router.post("/generate", response_model=TaskResponse, status_code=201)
def generate_task(request: TaskRequest):
    """Generate a new software engineering task via Gemini AI from a topic."""
    try:
        return task_service.generate_task(request)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Repository Analysis Endpoints ───────────────────────────────────

@router.post("/analyze/github", response_model=RepoAnalysisResponse, status_code=200)
def analyze_github(request: RepoAnalysisRequest):
    """
    Download and analyze a public GitHub repository.

    Performs strict SSRF verification, safe zip extraction, and recursive codebase analysis.
    """
    try:
        return repo_service.analyze_github_repository(str(request.repo_url))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/analyze/upload", response_model=RepoAnalysisResponse, status_code=200)
def analyze_upload(file: UploadFile = File(...)):
    """
    Analyze an uploaded repository ZIP file.

    Performs structural validation, magic byte verification, Zip-Slip prevention,
    and recursive codebase analysis.
    """
    filename = file.filename or "upload.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Only .zip archive uploads are supported."
        )

    try:
        return repo_service.analyze_uploaded_zip(file.file, filename=filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Contextual Repository Task Generation Endpoints ─────────────────

@router.post("/generate/from-repo", response_model=TaskResponse, status_code=201)
def generate_task_from_analysis(request: GenerateFromRepoRequest):
    """
    Generate a contextual coding task from an existing repository analysis.
    """
    try:
        return task_service.generate_task_from_repo(
            repo_analysis=request.repo_analysis,
            options=request.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/generate/github", response_model=TaskResponse, status_code=201)
def generate_task_from_github(request: GenerateFromGithubRequest):
    """
    Ingest, analyze, and generate a contextual coding task from a public GitHub repository in one call.
    """
    try:
        # Step 1: Ingest & analyze
        analysis = repo_service.analyze_github_repository(str(request.repo_url))
        # Step 2: Generate task
        return task_service.generate_task_from_repo(
            repo_analysis=analysis,
            options=request.options,
        )
    except ValueError as e:
        if "GEMINI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/generate/upload", response_model=TaskResponse, status_code=201)
def generate_task_from_upload(
    file: UploadFile = File(...),
    difficulty: Literal["easy", "medium", "hard"] = Form("medium"),
    focus_area: str | None = Form(None),
    category: str | None = Form(None),
):
    """
    Upload, analyze, and generate a contextual coding task from a ZIP archive in one call.
    """
    filename = file.filename or "upload.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Only .zip archive uploads are supported."
        )

    options = RepoTaskRequest(
        difficulty=difficulty,
        focus_area=focus_area,
        category=category,
    )

    try:
        # Step 1: Ingest & analyze
        analysis = repo_service.analyze_uploaded_zip(file.file, filename=filename)
        # Step 2: Generate task
        return task_service.generate_task_from_repo(
            repo_analysis=analysis,
            options=options,
        )
    except ValueError as e:
        if "GEMINI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Reference Solution Endpoint ─────────────────────────────────────

@router.post("/solution", response_model=SolutionResponse, status_code=201)
def generate_solution(request: SolutionRequest):
    """
    Generate a complete reference solution for a given coding task.

    Sends the task specification to Gemini and returns a structured,
    production-ready implementation with architecture notes, file-level
    code, a testing guide, and verification steps.
    """
    try:
        return solution_service.generate_reference_solution(request.task)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Automated Test Suite Endpoint ───────────────────────────────────

@router.post("/tests", response_model=TestSuiteResponse, status_code=201)
def generate_test_suite(request: TestSuiteRequest):
    """
    Generate an automated, repository-aware test suite for a given coding task.

    Synthesizes feature tests (verifying requirements & acceptance criteria) and
    regression checks (protecting baseline behavior) without executing code.
    """
    try:
        return test_service.generate_test_suite(
            task=request.task,
            solution=request.solution,
            repository_context=request.repo_analysis,
            framework=request.preferred_framework,
            starting_commit_sha=request.starting_commit_sha,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Validation Engine Endpoint ──────────────────────────────────────

@router.post("/validate", response_model=ValidationReport, status_code=200)
def validate_task_package(request: ValidationRequest):
    """
    Validate a task package (task + solution + test suite) through multi-gate validation.

    Enforces:
    - Path security and collision prevention.
    - Solution application integrity.
    - In static mode or without verified container isolation, safely returns NOT_VALIDATED.
    - Never executes untrusted code on the host machine.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="ctf_val_") as tmp_dir:
            workspace_root = Path(tmp_dir)

            # Pre-populate existing file targets from relevant_files if marked as existing
            for rel_file in request.task.relevant_files:
                clean_path = rel_file.replace(" (new)", "").replace(" (modified)", "").strip()
                if " (new)" not in rel_file and clean_path:
                    try:
                        p = validation_service.resolve_safe_workspace_path(workspace_root, clean_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        if not p.exists():
                            p.write_text("# existing file placeholder for validation\n", encoding="utf-8")
                    except ValueError:
                        pass

            report = validation_service.validate_task_package(
                workspace_root=workspace_root,
                request=request,
            )
            return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ── Harbor Task Package Export Endpoint ─────────────────────────────

@router.post("/export/harbor", status_code=200)
def export_harbor_task(request: HarborExportRequest):
    """
    Export a validated task package into official Harbor-compatible evaluation format.

    Generates:
    - task.toml (Harbor schema 1.4)
    - instruction.md (agent instructions without test leaks)
    - environment/Dockerfile (pinned starting commit SHA)
    - tests/test.sh (verifier with /logs/verifier/reward.txt protocol)
    - tests/feature/ and tests/regression/ test files
    - solution/solve.sh (oracle solution applier)
    - solution/files/ reference implementation

    Returns a downloadable, clean ZIP archive with Content-Disposition.
    All temporary build artifacts are cleaned up safely.
    Zero untrusted code is executed on the host.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="ctf_harbor_export_") as tmp_dir:
            zip_path, report = harbor_service.export_harbor_task_package(
                request, output_dir=tmp_dir
            )
            zip_bytes = zip_path.read_bytes()

        safe_filename = f"{harbor_service.sanitize_task_dirname(request.task_prefix, request.task.id)}.zip"

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Content-Length": str(len(zip_bytes)),
                "X-Harbor-Task-Name": report.harbor_task_name,
                "X-Validation-Status": report.validation_status_recorded,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Harbor export failed due to an unexpected server error.",
        )
