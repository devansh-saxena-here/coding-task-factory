from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.task import TaskResponse


class SolutionFile(BaseModel):
    path: str = Field(
        ...,
        description="Relative file path within the project (e.g. 'app/services/cache.py')",
        examples=["app/services/cache.py"],
    )
    status: Literal["create", "modify"] = Field(
        default="create",
        description="Whether this file should be created anew or modified from an existing file",
    )
    language: str = Field(
        default="python",
        description="Programming language of the code in this file",
        examples=["python", "typescript"],
    )
    code: str = Field(
        ...,
        description="Complete, production-ready code implementation for this file",
    )
    explanation: str = Field(
        ...,
        description="Explanation of the changes, design decisions, and how they fulfill requirements",
    )


class SolutionResponse(BaseModel):
    id: str = Field(..., description="Unique UUID identifier for this solution")
    task_id: str = Field(..., description="UUID of the task this solution solves")
    task_title: str = Field(..., description="Title of the task")
    architecture_notes: str = Field(
        ...,
        description="High-level architectural overview, component interactions, and design trade-offs",
    )
    files: list[SolutionFile] = Field(
        default_factory=list,
        description="List of file modifications and new files implementing the solution",
    )
    testing_guide: str = Field(
        ...,
        description="Guidance and instructions for writing tests to verify the solution",
    )
    verification_steps: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable steps to manually or automatically verify the solution satisfies acceptance criteria",
    )
    generated_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when the solution was generated",
    )


class SolutionRequest(BaseModel):
    task: TaskResponse = Field(
        ...,
        description="The generated coding task to produce a reference solution for",
    )
