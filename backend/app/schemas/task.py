from typing import Literal
from pydantic import BaseModel, Field, HttpUrl
from app.schemas.repo import RepoAnalysisResponse


class TaskRequest(BaseModel):
    topic: str
    difficulty: str = "medium"       # easy | medium | hard
    language: str = "python"
    category: str = "backend"        # backend | frontend | fullstack | devops | data


class RepoTaskRequest(BaseModel):
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    focus_area: str | None = Field(
        default=None,
        description="Optional focus area or feature to work on (e.g. 'authentication', 'caching')",
        examples=["Add rate limiting middleware"],
    )
    category: str | None = Field(
        default=None,
        description="Optional category override (e.g. backend, frontend, devops)",
        examples=["backend"],
    )


class GenerateFromRepoRequest(BaseModel):
    repo_analysis: RepoAnalysisResponse
    options: RepoTaskRequest = Field(default_factory=RepoTaskRequest)


class GenerateFromGithubRequest(BaseModel):
    repo_url: HttpUrl = Field(
        ...,
        description="Public GitHub repository URL (e.g., https://github.com/owner/repo)",
        examples=["https://github.com/fastapi/fastapi"],
    )
    options: RepoTaskRequest = Field(default_factory=RepoTaskRequest)


class TaskResponse(BaseModel):
    id: str
    topic: str
    difficulty: str
    language: str
    category: str
    title: str
    description: str
    requirements: list[str]
    acceptance_criteria: list[str]
    generated_at: str                 # ISO-8601 UTC timestamp
    project_name: str | None = None
    relevant_files: list[str] = Field(default_factory=list)
    starting_commit_sha: str | None = Field(
        default=None,
        description="Starting Git commit SHA when available",
        examples=["7fac3b2c12a84e3a4e402b8d9620b7c7b89d412e"],
    )
