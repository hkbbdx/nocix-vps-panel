from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..schemas import TaskCreate, TaskResponse, TaskUpdate
from ..security import require_api_key

router = APIRouter(prefix="/api/tasks", dependencies=[Depends(require_api_key)])


def manager(request: Request):
    return request.app.state.manager


def serialize(task):
    values = task.to_dict() if hasattr(task, "to_dict") else dict(task)
    return {
        key: values[key]
        for key in (
            "id",
            "goods_id",
            "stock_url",
            "cart_url",
            "target_price",
            "wait_interval",
            "operating_system",
            "email",
            "new_customer",
            "payment_method",
            "auto_submit",
            "password_configured",
            "status",
            "last_stock_status",
            "last_checked_at",
            "last_error",
        )
        if key in values
    }


def response(task):
    return TaskResponse(**serialize(task))


@router.get("", response_model=list[TaskResponse])
async def list_tasks(request: Request):
    return [response(task) for task in manager(request).repository.list_tasks()]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, request: Request):
    return response(manager(request).repository.create_task(payload))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request):
    task = manager(request).repository.get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return response(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, payload: TaskUpdate, request: Request):
    try:
        return response(await manager(request).update(task_id, payload))
    except KeyError as exc:
        raise HTTPException(404, "Task not found") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, request: Request):
    task_manager = manager(request)
    if task_manager.repository.get_task(task_id) is None:
        raise HTTPException(404, "Task not found")
    try:
        await task_manager.delete(task_id)
    except KeyError as exc:
        raise HTTPException(404, "Task not found") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def lifecycle(task_id: str, action: str, request: Request):
    try:
        result = await getattr(manager(request), action)(task_id)
        task = manager(request).repository.get_task(task_id)
        return {**result, "task": response(task) if task else None}
    except KeyError as exc:
        raise HTTPException(404, "Task not found") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{task_id}/start")
async def start_task(task_id: str, request: Request):
    return await lifecycle(task_id, "start", request)


@router.post("/{task_id}/pause")
async def pause_task(task_id: str, request: Request):
    return await lifecycle(task_id, "pause", request)


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, request: Request):
    return await lifecycle(task_id, "resume", request)


@router.post("/{task_id}/stop")
async def stop_task(task_id: str, request: Request):
    return await lifecycle(task_id, "stop", request)


@router.post("/{task_id}/check")
async def check_task(task_id: str, request: Request):
    return await lifecycle(task_id, "check_now", request)


@router.get("/{task_id}/history")
async def task_history(task_id: str, request: Request):
    task_manager = manager(request)
    if task_manager.repository.get_task(task_id) is None:
        raise HTTPException(404, "Task not found")
    return [record.__dict__ for record in task_manager.repository.list_task_orders(task_id)]
