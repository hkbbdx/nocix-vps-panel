from fastapi import APIRouter, Depends, Request

from ..security import require_api_key

router = APIRouter(prefix="/api")


@router.get("/stats", dependencies=[Depends(require_api_key)])
async def stats(request: Request):
    data = request.app.state.repository.get_stats()
    task_counts = data["task_counts"]
    order_counts = data["order_counts"]
    return {
        "worker_count": len(request.app.state.manager._workers),
        "task_count": sum(task_counts.values()),
        "available_count": data["available_count"],
        "checking_count": task_counts.get("checking", 0),
        "ordering_count": task_counts.get("ordering", 0),
        "success_count": task_counts.get("success", 0),
        "failure_count": task_counts.get("failed", 0),
        "order_success_count": order_counts.get("success", 0),
        "order_failure_count": order_counts.get("failed", 0),
        "last_error": data["last_error"],
    }


@router.get("/health", dependencies=[])
async def health(request: Request):
    return {"status": "ok"}
