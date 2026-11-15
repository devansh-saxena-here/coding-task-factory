from fastapi import APIRouter, HTTPException
from app.schemas.task import TaskRequest, TaskResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/")
def list_tasks():
    """List all generated tasks (placeholder — database coming in a future phase)."""
    return {"tasks": [], "message": "Task listing will be available in a future phase."}


@router.post("/generate", response_model=TaskResponse, status_code=201)
def generate_task(request: TaskRequest):
    """Generate a new software engineering task via Gemini AI."""
    try:
        return task_service.generate_task(request)
    except ValueError as e:
        # Missing API key — configuration problem
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        # Gemini API error or bad response
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        # Unexpected fallback
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
