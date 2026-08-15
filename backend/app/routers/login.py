from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..schemas import (
    EmailCodeRequest,
    LoginActionResponse,
    LoginStateResponse,
)
from ..security import require_api_key


router = APIRouter(prefix="/api/tasks", dependencies=[Depends(require_api_key)])

_PUBLIC_STATUSES = {
    "stopped",
    "running",
    "checking",
    "ordering",
    "login_first",
    "login_second",
    "waiting_for_email_code",
    "paused",
    "failed",
    "success",
    "unknown",
    "submitted_pending_confirmation",
}
_SAFE_ERRORS = {
    "email verification failed",
    "invalid verification code",
    "login verification is accepting a code",
    "login verification is not accepting a code",
    "login verification is not waiting",
    "login verification state is unavailable",
    "verification attempt already in flight",
    "verification cancelled",
}


def _manager(request: Request) -> Any:
    return request.app.state.manager


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise RuntimeError("invalid login state")


def _safe_error(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text in _SAFE_ERRORS else "login verification state is unavailable"


def _public_state(task_id: str, value: Any) -> LoginStateResponse:
    state = _mapping(value)
    raw_status = state.get("status")
    safe_status = raw_status if raw_status in _PUBLIC_STATUSES else "unknown"
    return LoginStateResponse(
        task_id=task_id,
        status=safe_status,
        waiting=bool(state.get("waiting")) and safe_status == "waiting_for_email_code",
        attempts=max(0, int(state.get("attempts", 0) or 0)),
        remaining_seconds=max(0, int(state.get("remaining_seconds", 0) or 0)),
        last_error=_safe_error(state.get("last_error")),
    )


async def _call(manager: Any, method_name: str, task_id: str, *args: Any) -> Any:
    result = getattr(manager, method_name)(task_id, *args)
    if inspect.isawaitable(result):
        return await result
    return result


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Task not found")


def _conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="Login verification is not available")


async def _state_or_error(manager: Any, task_id: str) -> LoginStateResponse:
    try:
        return _public_state(task_id, await _call(manager, "get_login_state", task_id))
    except KeyError as exc:
        raise _not_found() from exc
    except Exception as exc:
        raise _conflict() from exc


async def _action_state(
    manager: Any, task_id: str, fallback: LoginStateResponse, result: Any
) -> LoginStateResponse:
    try:
        return await _state_or_error(manager, task_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise
        return fallback.copy(update={"status": _result_status(result, fallback.status)})


def _result_mapping(result: Any) -> Mapping[str, Any]:
    return result if isinstance(result, Mapping) else {}


def _result_status(result: Any, fallback: str) -> str:
    status_value = _result_mapping(result).get("status")
    return status_value if status_value in _PUBLIC_STATUSES else fallback


def _accepted(result: Any) -> bool:
    return bool(_result_mapping(result).get("accepted"))


@router.get("/{task_id}/login-state", response_model=LoginStateResponse)
async def login_state(task_id: str, request: Request) -> LoginStateResponse:
    state = await _state_or_error(_manager(request), task_id)
    if not state.waiting:
        raise _conflict()
    return state


@router.post("/{task_id}/email-code", response_model=LoginActionResponse)
async def submit_email_code(
    task_id: str, payload: EmailCodeRequest, request: Request
) -> LoginActionResponse:
    task_manager = _manager(request)
    current = await _state_or_error(task_manager, task_id)
    if not current.waiting:
        raise _conflict()

    try:
        result = await _call(task_manager, "submit_email_code", task_id, payload.code)
    except KeyError as exc:
        raise _not_found() from exc
    except Exception as exc:
        raise _conflict() from exc

    if not _accepted(result):
        raise _conflict()

    state = await _action_state(task_manager, task_id, current, result)
    return LoginActionResponse(
        **state.dict(),
        result="accepted",
        message="verification accepted",
    )


@router.post("/{task_id}/login-cancel", response_model=LoginActionResponse)
async def cancel_login(task_id: str, request: Request) -> LoginActionResponse:
    task_manager = _manager(request)
    current = await _state_or_error(task_manager, task_id)
    if not current.waiting:
        raise _conflict()

    try:
        result = await _call(task_manager, "cancel_login", task_id)
    except KeyError as exc:
        raise _not_found() from exc
    except Exception as exc:
        raise _conflict() from exc

    if not _accepted(result):
        raise _conflict()

    state = await _action_state(task_manager, task_id, current, result)
    if state.last_error is None:
        state = state.copy(update={"last_error": "verification cancelled"})
    return LoginActionResponse(
        **state.dict(),
        result="cancelled",
        message="verification cancelled",
    )
