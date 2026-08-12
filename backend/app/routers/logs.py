from fastapi import APIRouter, Depends, Query, Request, Response, status

from ..security import require_api_key

router = APIRouter(prefix="/api/logs", dependencies=[Depends(require_api_key)])


@router.get("")
async def list_logs(
    request: Request,
    task_id: str | None = None,
    level: str | None = None,
    limit: int = Query(default=100, ge=0, le=500),
):
    return [
        record.__dict__
        for record in request.app.state.repository.list_logs(task_id, level, limit)
    ]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_logs(request: Request):
    request.app.state.repository.clear_logs()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
