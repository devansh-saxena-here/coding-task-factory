from pydantic import BaseModel


class TaskRequest(BaseModel):
    topic: str
    difficulty: str = "medium"       # easy | medium | hard
    language: str = "python"
    category: str = "backend"        # backend | frontend | fullstack | devops | data


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
