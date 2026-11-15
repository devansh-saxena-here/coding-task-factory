"""
Task generation service.

Phase 1 (current): stub that raises NotImplementedError.
Phase 2 (Day 3):   replace the body of generate_task() with an LLM API call.
"""
from app.schemas.task import TaskRequest, TaskResponse


def generate_task(request: TaskRequest) -> TaskResponse:
    """Generate a coding task using an AI model (not yet implemented)."""
    raise NotImplementedError("AI task generation will be implemented in Day 3.")
