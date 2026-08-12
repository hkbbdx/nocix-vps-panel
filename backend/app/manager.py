from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass
from typing import Any, Callable

from .redaction import redact_message
from .repositories import Repository, TaskRecord
from .schemas import TaskUpdate
from .worker import CheckoutWorker


@dataclass
class WorkerHandle:
    worker_task: asyncio.Task
    stop_event: threading.Event
    pause_event: threading.Event
    worker: Any
    preserve_restart_marker: bool = False
    restartable: bool = True
    stopping: bool = False


class SingleCheckWorker:
    """One stock request with no checkout loop or order submission."""

    def __init__(self, task, *, client_factory, repository, stop_event, pause_event):
        self.task = task
        self.client_factory = client_factory
        self.repository = repository
        self.stop_event = stop_event
        self.pause_event = pause_event

    def run(self):
        if self.stop_event.is_set() or self.pause_event.is_set():
            return
        client = None
        try:
            self.repository.set_task_status(self.task.id, "checking")
            client = self.client_factory()
            stock_url = getattr(self.task, "stock_url", None)
            method = client.check_stock
            if stock_url:
                try:
                    parameters = inspect.signature(method).parameters.values()
                    accepts_url = len(list(parameters)) >= 2
                except (TypeError, ValueError):
                    accepts_url = True
                available = bool(
                    method(self.task.goods_id, stock_url)
                    if accepts_url
                    else method(self.task.goods_id)
                )
            else:
                available = bool(method(self.task.goods_id))
            self.repository.set_task_check_result(
                self.task.id, "available" if available else "out_of_stock"
            )
        except Exception as exc:
            self.repository.set_task_status(
                self.task.id, "failed", error=redact_message(str(exc))
            )
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass


class TaskManager:
    INDETERMINATE_STATUSES = {"unknown", "submitted_pending_confirmation"}
    ACTIVE_STATUSES = {"running", "checking", "ordering"}

    def __init__(
        self,
        repository: Repository,
        *,
        settings: Any = None,
        worker_factory: Callable[..., Any] | None = None,
        check_factory: Callable[..., Any] | None = None,
        stop_timeout: float = 5.0,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.stop_timeout = stop_timeout
        self._workers: dict[str, WorkerHandle] = {}
        self._lock = asyncio.Lock()
        self._worker_factory = worker_factory or self._default_worker_factory
        self._check_factory = check_factory or self._default_check_factory
        self._shutdown = False

    def _default_worker_factory(self, task, stop_event, pause_event):
        from nocix_fucker.client import Client

        client_factory = lambda: Client(self.settings.browser_dsn, None)
        return CheckoutWorker(
            task,
            client_factory=client_factory,
            repository=self.repository,
            stop_event=stop_event,
            pause_event=pause_event,
            logger=lambda level, message: self.repository.append_log(level, task.id, message),
        )

    def _default_check_factory(self, task, stop_event, pause_event):
        from nocix_fucker.client import Client

        return SingleCheckWorker(
            task,
            client_factory=lambda: Client(self.settings.browser_dsn, None),
            repository=self.repository,
            stop_event=stop_event,
            pause_event=pause_event,
        )

    def _task_or_404(self, task_id: str) -> TaskRecord:
        task = self.repository.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    async def _run_worker(self, task_id: str, worker: Any) -> None:
        thread_task = asyncio.create_task(asyncio.to_thread(worker.run))
        try:
            await asyncio.shield(thread_task)
        except asyncio.CancelledError:
            await asyncio.shield(thread_task)
            raise
        except Exception as exc:
            if not getattr(worker, "_persistence_blocked", False):
                try:
                    self.repository.set_task_lifecycle(
                        task_id,
                        "failed",
                        running_before_shutdown=False,
                        error=redact_message(str(exc)),
                    )
                except KeyError:
                    pass
        finally:
            async with self._lock:
                handle = self._workers.get(task_id)
                if handle is not None and handle.worker is worker:
                    if not getattr(worker, "_persistence_blocked", False):
                        self._workers.pop(task_id, None)
                        if not handle.preserve_restart_marker:
                            try:
                                task = self.repository.get_task(task_id)
                                if task is not None and task.status in {
                                    "running",
                                    "checking",
                                    "ordering",
                                }:
                                    self.repository.set_task_lifecycle(
                                        task_id,
                                        "stopped",
                                        running_before_shutdown=False,
                                    )
                                self.repository.set_running_before_shutdown(task_id, False)
                            except KeyError:
                                pass

    async def _start_locked(self, task: TaskRecord) -> dict:
        if self._shutdown:
            raise RuntimeError("manager is shut down")
        if task.status in {"success"} | self.INDETERMINATE_STATUSES:
            raise RuntimeError(f"task cannot start from {task.status}")
        existing = self._workers.get(task.id)
        if existing is not None:
            if getattr(existing.worker, "_persistence_blocked", False):
                raise RuntimeError("task is still owned after submission persistence failure")
            if not existing.worker_task.done():
                if existing.stopping:
                    raise RuntimeError("task is still owned by a worker")
                return {"started": False, "idempotent": True, "status": task.status}
            self._workers.pop(task.id, None)
        if task.status not in {"stopped", "failed", "paused"}:
            raise RuntimeError(f"task cannot start from {task.status}")
        stop_event = threading.Event()
        pause_event = threading.Event()
        worker = self._worker_factory(task, stop_event, pause_event)
        self.repository.set_task_lifecycle(
            task.id, "running", running_before_shutdown=True
        )
        worker_task = asyncio.create_task(self._run_worker(task.id, worker))
        self._workers[task.id] = WorkerHandle(
            worker_task=worker_task,
            stop_event=stop_event,
            pause_event=pause_event,
            worker=worker,
        )
        return {"started": True, "idempotent": False, "status": "running"}

    async def start(self, task_id: str) -> dict:
        async with self._lock:
            task = self._task_or_404(task_id)
            return await self._start_locked(task)

    async def update(self, task_id: str, patch: TaskUpdate) -> TaskRecord:
        async with self._lock:
            task = self._task_or_404(task_id)
            if task.status in {"success"} | self.INDETERMINATE_STATUSES | self.ACTIVE_STATUSES:
                if task_id in self._workers:
                    raise RuntimeError("task is still owned by a worker")
                raise RuntimeError(f"cannot update terminal task in {task.status} state")
            if task_id in self._workers:
                raise RuntimeError("task is still owned by a worker")
            return self.repository.update_task(task_id, patch)

    async def pause(self, task_id: str) -> dict:
        async with self._lock:
            task = self._task_or_404(task_id)
            if task.status in self.INDETERMINATE_STATUSES:
                raise RuntimeError(f"task cannot pause from {task.status}")
            handle = self._workers.get(task_id)
            if handle is not None and getattr(handle.worker, "_persistence_blocked", False):
                raise RuntimeError("task is retained after submission persistence failure")
            if handle is None:
                if task.status == "paused":
                    return {"status": "paused"}
                raise RuntimeError("task is not running")
            if task.status not in {"running", "checking", "ordering"}:
                raise RuntimeError(f"task cannot pause from {task.status}")
            self.repository.pause_task(
                task_id, expected_marker=task.running_before_shutdown
            )
            handle.pause_event.set()
            worker_task = handle.worker_task
            handle.preserve_restart_marker = False
            handle.stopping = True
        if not await self._await_bounded(worker_task):
            raise RuntimeError("worker did not stop within timeout")
        return {"status": "paused"}

    async def resume(self, task_id: str) -> dict:
        async with self._lock:
            task = self._task_or_404(task_id)
            if task.status in self.INDETERMINATE_STATUSES:
                raise RuntimeError(f"task cannot resume from {task.status}")
            if task.status != "paused":
                raise RuntimeError("task is not paused")
        return await self.start(task_id)

    async def stop(self, task_id: str) -> dict:
        async with self._lock:
            task = self._task_or_404(task_id)
            if task.status in self.INDETERMINATE_STATUSES:
                raise RuntimeError(f"cannot stop terminal task in {task.status} state")
            handle = self._workers.get(task_id)
            if handle is not None and getattr(handle.worker, "_persistence_blocked", False):
                raise RuntimeError("task is retained after submission persistence failure")
            if task.status in {"success", "failed"}:
                raise RuntimeError(f"cannot stop terminal task in {task.status} state")
            self.repository.stop_task(task_id)
            if handle is not None:
                handle.stop_event.set()
                worker_task = handle.worker_task
                handle.preserve_restart_marker = False
                handle.stopping = True
            else:
                worker_task = None
        if worker_task is not None:
            if not await self._await_bounded(worker_task):
                raise RuntimeError("worker did not stop within timeout")
        return {"status": "stopped"}

    async def delete(self, task_id: str) -> None:
        async with self._lock:
            task = self._task_or_404(task_id)
            handle = self._workers.get(task_id)
            if handle is None:
                self.repository.delete_task(task_id)
                return
            handle.stop_event.set()
            handle.preserve_restart_marker = False
            handle.stopping = True
            if task.status not in self.INDETERMINATE_STATUSES:
                self.repository.stop_task(task_id)
            worker_task = handle.worker_task
        if not await self._await_bounded(worker_task):
            raise RuntimeError("worker did not stop within timeout")
        async with self._lock:
            if self.repository.get_task(task_id) is None:
                raise KeyError(task_id)
            if task_id in self._workers:
                raise RuntimeError("worker is still owned by a task")
            self.repository.delete_task(task_id)

    async def check_now(self, task_id: str) -> dict:
        async with self._lock:
            task = self._task_or_404(task_id)
            if task.status in {
                "success",
                "failed",
            } | self.INDETERMINATE_STATUSES:
                raise RuntimeError(f"cannot check terminal task in {task.status} state")
            if task_id in self._workers:
                raise RuntimeError("task already has a worker")
            if self._shutdown:
                raise RuntimeError("manager is shut down")
            stop_event = threading.Event()
            pause_event = threading.Event()
            worker = self._check_factory(task, stop_event, pause_event)
            self.repository.set_task_lifecycle(
                task_id, "running", running_before_shutdown=False
            )
            worker_task = asyncio.create_task(self._run_worker(task_id, worker))
            self._workers[task_id] = WorkerHandle(
                worker_task=worker_task,
                stop_event=stop_event,
                pause_event=pause_event,
                worker=worker,
                restartable=False,
            )
            return {"started": True, "idempotent": False, "status": "running"}

    async def _await_bounded(self, worker_task: asyncio.Task | None) -> bool:
        if worker_task is None:
            return True
        try:
            await asyncio.wait_for(asyncio.shield(worker_task), timeout=self.stop_timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def recover_stale_tasks(self) -> int:
        async with self._lock:
            recovery_tasks = self.repository.list_recovery_tasks()
            for task in recovery_tasks:
                if task.running_before_shutdown:
                    self.repository.set_task_lifecycle(
                        task.id, "stopped", running_before_shutdown=False
                    )
                    await self._start_locked(self.repository.get_task(task.id))
                else:
                    self.repository.set_task_lifecycle(
                        task.id, "stopped", running_before_shutdown=False
                    )
            return len(recovery_tasks)

    def owned_worker_count(self) -> int:
        """Return active or retained worker handles, including non-cooperative threads."""
        return len(self._workers)

    async def shutdown(self) -> None:
        async with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            handles = [
                (task_id, handle)
                for task_id, handle in self._workers.items()
                if not handle.worker_task.done()
            ]
            for task_id, handle in handles:
                current = self.repository.get_task(task_id)
                if current is None:
                    continue
                is_terminal = current.status in {"success", "failed"}
                is_active = current.status in {"running", "checking", "ordering"}
                should_restart = (
                    is_active
                    and
                    handle.restartable
                    and not handle.stopping
                    and not handle.pause_event.is_set()
                )
                handle.stop_event.set()
                handle.stopping = True
                handle.preserve_restart_marker = should_restart
                if not getattr(handle.worker, "_persistence_blocked", False):
                    self.repository.shutdown_task_lifecycle(
                        task_id,
                        expected_marker=current.running_before_shutdown,
                        running_before_shutdown=should_restart,
                    )
        results = await asyncio.gather(
            *(self._await_bounded(handle.worker_task) for _, handle in handles),
            return_exceptions=True,
        )
        for (task_id, handle), completed in zip(handles, results):
            if completed is not True:
                handle.preserve_restart_marker = False
                try:
                    self.repository.set_running_before_shutdown(task_id, False)
                except KeyError:
                    pass
