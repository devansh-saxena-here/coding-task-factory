from pydantic import BaseModel


class TaskRequest(BaseModel):
    topic: str
    difficulty: str = "medium"   # easy | medium | hard
    language: str = "python"


class TaskResponse(BaseModel):
    id: str
    topic: str
    difficulty: str
    language: str
    title: str
    description: str
    examples: list[str]
    constraints: list[str]
