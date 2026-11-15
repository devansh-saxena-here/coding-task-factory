from fastapi import APIRouter, HTTPException
from app.schemas.task import TaskRequest, TaskResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/")
def list_tasks():
    """List all generated tasks (placeholder)."""
    return {"tasks": [], "message": "Task listing will be available after Day 3."}


@router.post("/generate", response_model=TaskResponse, status_code=201)
def generate_task(request: TaskRequest):
    """Generate a new coding task via AI (stub — Day 3 will implement the LLM call)."""
    try:
        return task_service.generate_task(request)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
