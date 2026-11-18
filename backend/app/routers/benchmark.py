"""
Benchmark Router — Day 11 Step 5.

Exposes the AI Coding Agent Evaluation Orchestrator via FastAPI endpoints:
- GET /benchmark/agents: List registered agent configurations
- POST /benchmark/runs: Create and initiate a benchmark evaluation run
- GET /benchmark/runs/{run_id}: Inspect run status, scorecards, and reports
- POST /benchmark/runs/{run_id}/cancel: Cancel an in-flight benchmark evaluation

Enforces strict input validation, non-blocking execution, and zero secret leakage.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.orchestrator.adapters.mock import MockReplayAdapter
from app.orchestrator.run_manager import RunManager
from app.schemas.orchestrator import (
    AgentListResponse,
    AgentSummary,
    BenchmarkReport,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    CancelRunResponse,
)
from app.services import task_service

router = APIRouter(prefix="/benchmark", tags=["Benchmark"])

# ── Singleton RunManager Dependency ──────────────────────────────────
_GLOBAL_RUN_MANAGER = RunManager(pre_register_defaults=True)


def get_run_manager() -> RunManager:
    """Dependency provider guaranteeing a single consistent RunManager instance."""
    return _GLOBAL_RUN_MANAGER


# ── 1. List Registered Agents ────────────────────────────────────────

@router.get(
    "/agents",
    response_model=AgentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available AI coding agents",
    description="Returns public identifiers and names of registered agent adapters. Never exposes secrets or internal credentials.",
)
def list_agents(
    manager: RunManager = Depends(get_run_manager),
) -> AgentListResponse:
    """Returns summaries of all registered agent adapters."""
    summaries: list[AgentSummary] = []

    for adapter in manager.list_adapters():
        is_mock = isinstance(adapter, MockReplayAdapter)
        desc = (
            "Deterministic mock simulation adapter (no live model execution)."
            if is_mock
            else "Configured agent adapter harness."
        )
        summaries.append(
            AgentSummary(
                agent_id=adapter.agent_id,
                display_name=adapter.display_name,
                is_simulated=is_mock,
                description=desc,
            )
        )

    return AgentListResponse(agents=summaries)


# ── 2. Create & Start Benchmark Run ──────────────────────────────────

@router.post(
    "/runs",
    response_model=BenchmarkRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate a multi-agent benchmark run",
    description="Queues a benchmark run across registered agents against a specified task. Executes sequentially in the background.",
)
async def create_benchmark_run(
    request: BenchmarkRunRequest,
    background_tasks: BackgroundTasks,
    manager: RunManager = Depends(get_run_manager),
) -> BenchmarkRunResponse:
    """
    Creates and initiates an asynchronous benchmark evaluation run.
    
    Validates task existence and agent availability, queueing sequential execution.
    """
    # 1. Validate task existence in task repository
    task = task_service.get_task(request.task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{request.task_id}' was not found. Please create or generate the task first.",
        )

    # 2. Validate requested agents against registered adapters
    registered_ids = {a.agent_id for a in manager.list_adapters()}
    for aid in request.agent_config_ids:
        if aid not in registered_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown agent configuration ID '{aid}'. Available agents: {sorted(list(registered_ids))}",
            )

    # 3. Create run record in RunManager
    try:
        run_resp = manager.create_benchmark_run(request, task)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # 4. Schedule non-blocking execution via FastAPI BackgroundTasks
    background_tasks.add_task(manager.execute_benchmark_run, run_resp.run_id, task)

    return run_resp


# ── 3. Inspect Benchmark Run & Scorecard ──────────────────────────────

@router.get(
    "/runs/{run_id}",
    response_model=BenchmarkReport,
    status_code=status.HTTP_200_OK,
    summary="Retrieve benchmark run report and scorecards",
    description="Returns full execution metrics, test pass rates, diff quality, diagnostics, and ranking.",
)
def get_benchmark_run(
    run_id: str,
    manager: RunManager = Depends(get_run_manager),
) -> BenchmarkReport:
    """Retrieves the complete status and scorecard report for a benchmark run."""
    try:
        return manager.get_report(run_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run with ID '{run_id}' was not found.",
        )


# ── 4. Cancel Active Benchmark Run ───────────────────────────────────

@router.post(
    "/runs/{run_id}/cancel",
    response_model=CancelRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an active benchmark evaluation run",
    description="Aborts queued and running agent executions within the specified benchmark run.",
)
async def cancel_benchmark_run(
    run_id: str,
    manager: RunManager = Depends(get_run_manager),
) -> CancelRunResponse:
    """Issues cancellation for an in-flight or queued benchmark run."""
    try:
        # Check run existence
        manager.get_run(run_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run with ID '{run_id}' was not found.",
        )

    cancelled = await manager.cancel_run(run_id)
    report = manager.get_report(run_id)

    msg = (
        "Cancellation request processed successfully."
        if cancelled
        else "Run was already completed or could not be cancelled."
    )

    return CancelRunResponse(
        run_id=run_id,
        status=report.status,
        message=msg,
    )
