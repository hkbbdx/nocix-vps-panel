from fastapi import APIRouter, Depends, Query, Request, Response, status

from ..security import require_api_key

router = APIRouter(prefix="/api/orders", dependencies=[Depends(require_api_key)])


@router.get("")
async def list_orders(
    request: Request,
    task_id: str | None = None,
    order_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=0, le=500),
):
    return [
        record.__dict__
        for record in request.app.state.repository.list_orders(
            task_id=task_id, status=order_status, limit=limit
        )
    ]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_orders(request: Request):
    request.app.state.repository.clear_orders()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
