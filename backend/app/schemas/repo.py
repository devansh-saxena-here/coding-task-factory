from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class RepoAnalysisRequest(BaseModel):
    repo_url: HttpUrl = Field(
        ...,
        description="Public GitHub repository URL (e.g., https://github.com/owner/repo)",
        examples=["https://github.com/fastapi/fastapi"],
    )


class RepoAnalysisResponse(BaseModel):
    project_name: str = Field(..., description="Name of the project or repository")
    source_type: Literal["github", "zip"] = Field(
        ..., description="Source of the codebase ('github' or 'zip')"
    )
    detected_languages: list[str] = Field(
        default_factory=list, description="Primary programming languages detected"
    )
    detected_frameworks: list[str] = Field(
        default_factory=list, description="Frameworks or libraries detected (e.g., FastAPI, React)"
    )
    file_count: int = Field(default=0, ge=0, description="Total count of analyzed files")
    folder_structure: list[str] = Field(
        default_factory=list, description="High-level project folder hierarchy"
    )
    readme_summary: str | None = Field(
        default=None, description="Extracted or truncated content from README file if present"
    )
    analysis_status: Literal["pending", "completed", "failed"] = Field(
        default="completed", description="Status of the repository analysis"
    )
    commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA of the analyzed repository state when available",
        examples=["7fac3b2c12a84e3a4e402b8d9620b7c7b89d412e"],
    )
