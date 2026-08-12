import asyncio
import threading
from dataclasses import dataclass, field

import httpx
import pytest
from cryptography.fernet import Fernet

from backend.app.config import Settings
from backend.app.db import create_engine, create_session_factory, init_db
from backend.app.main import create_app
from backend.app.manager import SingleCheckWorker, TaskManager
from backend.app.repositories import Repository
from backend.app.schemas import TaskCreate, TaskUpdate
from backend.app.worker import CheckoutWorker


def task_data(password="plain-password"):
    return TaskCreate(
        goods_id="418",
        target_price=59,
        wait_interval=5,
        email="buyer@example.com",
        password=password,
    )


@pytest.fixture
def repository(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        api_key="test-api-key",
        data_encryption_key=key,
        data_dir=str(tmp_path),
    )
    engine = create_engine(settings, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    try:
        yield Repository(create_session_factory(engine), settings), settings
    finally:
        engine.dispose()


@dataclass
class BlockingWorker:
    task: object
    stop_event: object
    pause_event: object
    started: list = field(default_factory=list)
    run_count: int = 0

    def run(self):
        self.run_count += 1
        self.started.append(self.task.id)
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                return
            import time

            time.sleep(0.005)


@dataclass
class NonCooperativeWorker:
    task: object
    stop_event: object
    pause_event: object
    release: threading.Event
    started: threading.Event = field(default_factory=threading.Event)

    def run(self):
        self.started.set()
        self.release.wait(timeout=5)


@dataclass
class RaisingWorker:
    task: object
    stop_event: object
    pause_event: object

    def run(self):
        raise RuntimeError("password=worker-secret token=worker-token")


@dataclass
class OneShotWorker:
    task: object
    stop_event: object
    pause_event: object
    calls: list

    def run(self):
        self.calls.append(self.task.id)


@dataclass
class TerminalBeforeShutdownWorker:
    task: object
    stop_event: object
    pause_event: object
    repository: object
    terminal_status: str
    release: threading.Event
    persisted: threading.Event = field(default_factory=threading.Event)

    def run(self):
        self.repository.set_task_status(self.task.id, self.terminal_status)
        self.persisted.set()
        self.release.wait(timeout=5)


class SubmitClient:
    current_url = "https://nocix.net/cart/?id=418"
    last_price_text = None

    def __init__(self):
        self.submit_calls = 0

    def check_stock(self, goods_id, stock_url=None):
        return True

    def open_cart(self, goods_id, cart_url=None):
        return None

    def select_operating_system(self, value):
        return True

    def match_price(self, target_price):
        return True

    def fill_in_customer_info(self, **kwargs):
        return None

    def fill_in_payment_info(self, **kwargs):
        return None

    def click_next_step_button(self):
        return None

    def submit_order(self):
        self.submit_calls += 1
        return None

    def close(self):
        return None


class OutOfStockClient:
    current_url = "https://nocix.net/cart/?id=418"
    last_price_text = None

    def __init__(self):
        self.check_calls = 0

    def check_stock(self, goods_id, stock_url=None):
        self.check_calls += 1
        return False

    def close(self):
        return None


async def wait_until(predicate, timeout=1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        await asyncio.sleep(0.005)


def test_starting_same_task_twice_creates_one_worker(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        first = await manager.start(record.id)
        second = await manager.start(record.id)
        await manager.stop(record.id)
        return first, second, manager

    first, second, manager = asyncio.run(exercise())

    assert first["started"] is True
    assert second["started"] is False
    assert second["idempotent"] is True
    assert len(created) == 1
    assert repo.get_task(record.id).status == "stopped"
    asyncio.run(manager.shutdown())


def test_default_worker_factory_persists_lifecycle_logs(repository, monkeypatch):
    repo, settings = repository
    record = repo.create_task(task_data(password="worker-password"))
    client = OutOfStockClient()
    monkeypatch.setattr("nocix_fucker.client.Client", lambda dsn, proxy: client)
    manager = TaskManager(repo, settings=settings)
    stop_event = threading.Event()
    pause_event = threading.Event()
    worker = manager._default_worker_factory(record, stop_event, pause_event)
    worker.sleep = lambda seconds: stop_event.set()

    async def exercise():
        worker.run()

    asyncio.run(exercise())

    messages = [log.message for log in repo.list_logs(record.id, None, 20)]
    assert any("checkout worker started" in message for message in messages)
    assert any("out_of_stock" in message for message in messages)
    assert all("worker-password" not in message for message in messages)


def test_explicit_start_retries_an_ordinary_failed_task(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, "failed", error="price mismatch")
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        result = await manager.start(record.id)
        await manager.stop(record.id)
        await manager.shutdown()
        return result

    result = asyncio.run(exercise())

    assert result["started"] is True
    assert len(created) == 1


def test_post_submit_persistence_failure_retains_manager_ownership(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    client = SubmitClient()
    original_set_status = repo.set_task_status

    def fail_terminal_status(task_id, status, error=None):
        if status in {"success", "failed", "unknown", "submitted_pending_confirmation"}:
            raise RuntimeError("database unavailable")
        return original_set_status(task_id, status, error)

    repo.set_task_status = fail_terminal_status
    repo.create_order = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("database unavailable")
    )
    repo.finalize_submission = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("database unavailable")
    )

    def worker_factory(task, stop_event, pause_event):
        return CheckoutWorker(
            task,
            client_factory=lambda: client,
            repository=repo,
            stop_event=stop_event,
            pause_event=pause_event,
        )

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        await manager.start(record.id)
        await wait_until(lambda: manager._workers[record.id].worker_task.done())
        current = repo.get_task(record.id)
        with pytest.raises(RuntimeError, match="owned"):
            await manager.start(record.id)
        return manager, current

    manager, current = asyncio.run(exercise())

    assert client.submit_calls == 1
    assert manager.owned_worker_count() == 1
    assert current.status == "ordering"
    assert current.status not in {"stopped", "failed"}


def test_concurrent_starts_create_one_worker(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        results = await asyncio.gather(manager.start(record.id), manager.start(record.id))
        await manager.stop(record.id)
        return results

    results = asyncio.run(exercise())

    assert len(created) == 1
    assert sorted(result["started"] for result in results) == [False, True]


def test_non_cooperative_stop_timeout_retains_ownership_and_record(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = NonCooperativeWorker(task, stop_event, pause_event, release)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=worker_factory,
            stop_timeout=0.02,
        )
        await manager.start(record.id)
        await wait_until(lambda: created[0].started.is_set())
        with pytest.raises(RuntimeError, match="did not stop"):
            await manager.stop(record.id)
        with pytest.raises(RuntimeError, match="still owned"):
            await manager.start(record.id)
        with pytest.raises(RuntimeError, match="did not stop"):
            await manager.delete(record.id)
        assert repo.get_task(record.id) is not None
        release.set()
        await manager._workers[record.id].worker_task
        await manager.delete(record.id)
        await manager.shutdown()

    asyncio.run(exercise())
    assert repo.get_task(record.id) is None


def test_shutdown_is_bounded_for_non_cooperative_worker(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = NonCooperativeWorker(task, stop_event, pause_event, release)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=worker_factory,
            stop_timeout=0.02,
        )
        await manager.start(record.id)
        await wait_until(lambda: created[0].started.is_set())
        started_at = asyncio.get_running_loop().time()
        await manager.shutdown()
        elapsed = asyncio.get_running_loop().time() - started_at
        handle = manager._workers[record.id]
        assert elapsed < 0.2
        assert not handle.worker_task.done()
        assert repo.get_task(record.id).running_before_shutdown is False
        with pytest.raises(RuntimeError, match="shut down"):
            await manager.start(record.id)
        release.set()
        await handle.worker_task

    asyncio.run(exercise())


@pytest.mark.parametrize("terminal_status", ["success", "failed"])
def test_shutdown_does_not_overwrite_terminal_state_persisted_by_worker(
    repository, terminal_status
):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = TerminalBeforeShutdownWorker(
            task,
            stop_event,
            pause_event,
            repo,
            terminal_status,
            release,
        )
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=worker_factory,
            stop_timeout=0.02,
        )
        await manager.start(record.id)
        await wait_until(lambda: created[0].persisted.is_set())
        await manager.shutdown()
        assert repo.get_task(record.id).status == terminal_status
        release.set()
        await manager._workers[record.id].worker_task

    asyncio.run(exercise())


@pytest.mark.parametrize("terminal_status", ["success", "failed"])
def test_shutdown_conditional_update_wins_terminal_transition_race(
    repository, terminal_status
):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()
    original_shutdown_update = repo.shutdown_task_lifecycle

    def race_update(task_id, *, expected_marker, running_before_shutdown):
        repo.set_task_status(task_id, terminal_status)
        return original_shutdown_update(
            task_id,
            expected_marker=expected_marker,
            running_before_shutdown=running_before_shutdown,
        )

    repo.shutdown_task_lifecycle = race_update

    def worker_factory(task, stop_event, pause_event):
        return NonCooperativeWorker(task, stop_event, pause_event, release)

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=worker_factory,
            stop_timeout=0.02,
        )
        await manager.start(record.id)
        await manager.shutdown()
        result = repo.get_task(record.id)
        release.set()
        await manager._workers[record.id].worker_task
        return result

    result = asyncio.run(exercise())

    assert result.status == terminal_status
    assert result.running_before_shutdown is False


def test_concurrent_delete_allows_one_delete_and_maps_other_to_missing(repository):
    repo, settings = repository
    record = repo.create_task(task_data())

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        results = await asyncio.gather(
            manager.delete(record.id), manager.delete(record.id), return_exceptions=True
        )
        return results

    results = asyncio.run(exercise())

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, KeyError) for result in results) == 1
    assert repo.get_task(record.id) is None


def test_concurrent_owned_delete_has_one_success_and_one_missing(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = NonCooperativeWorker(task, stop_event, pause_event, release)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=worker_factory,
            stop_timeout=0.5,
        )
        await manager.start(record.id)
        await wait_until(lambda: created[0].started.is_set())
        release.set()
        results = await asyncio.gather(
            manager.delete(record.id), manager.delete(record.id), return_exceptions=True
        )
        await manager.shutdown()
        return results

    results = asyncio.run(exercise())

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, KeyError) for result in results) == 1
    assert repo.get_task(record.id) is None


@pytest.mark.parametrize("terminal_status", ["success", "failed"])
def test_stop_and_check_reject_terminal_tasks(repository, terminal_status):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, terminal_status)

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.stop(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.check_now(record.id)

    asyncio.run(exercise())
    assert repo.get_task(record.id).status == terminal_status


@pytest.mark.parametrize("terminal_status", ["submitted_pending_confirmation", "unknown"])
def test_start_and_check_reject_indeterminate_submission(repository, terminal_status):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, terminal_status, error="submission outcome is unknown")

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.start(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.check_now(record.id)

    asyncio.run(exercise())
    assert repo.get_task(record.id).status == terminal_status


@pytest.mark.parametrize("terminal_status", ["submitted_pending_confirmation", "unknown"])
def test_indeterminate_submission_rejects_stop_start_and_check_without_mutation(
    repository, terminal_status
):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, terminal_status, error="submission outcome is unknown")

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.stop(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.start(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.check_now(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.pause(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.resume(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.update(record.id, TaskUpdate(target_price=70))

    asyncio.run(exercise())
    assert repo.get_task(record.id).status == terminal_status


def test_update_rejects_success_task_as_terminal_without_mutation(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, "success")

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        with pytest.raises(RuntimeError, match="success"):
            await manager.update(record.id, TaskUpdate(target_price=70))

    asyncio.run(exercise())

    current = repo.get_task(record.id)
    assert current.status == "success"
    assert current.target_price == 59


@pytest.mark.parametrize(
    "terminal_status, order_status",
    [("success", "success"), ("submitted_pending_confirmation", "unknown")],
)
def test_pause_race_does_not_overwrite_worker_terminal_finalization(
    repository, terminal_status, order_status
):
    repo, settings = repository
    record = repo.create_task(task_data())

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=BlockingWorker)
        await manager.start(record.id)
        original_pause = getattr(repo, "pause_task", None)

        def finalize_before_pause(task_id, *, expected_marker):
            repo.set_task_status(task_id, terminal_status, error="submission outcome is unknown")
            repo.create_order(task_id, order_status, "59.00", "submission outcome is unknown")
            if original_pause is None:
                return repo.set_task_lifecycle(
                    task_id, "paused", running_before_shutdown=False
                )
            return original_pause(task_id, expected_marker=expected_marker)

        repo.pause_task = finalize_before_pause
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.pause(record.id)

        current = repo.get_task(record.id)
        assert current.status == terminal_status
        assert current.running_before_shutdown is False
        assert repo.list_task_orders(record.id)[-1].status == order_status
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.start(record.id)
        with pytest.raises(RuntimeError, match=terminal_status):
            await manager.check_now(record.id)

        handle = manager._workers[record.id]
        handle.stop_event.set()
        await handle.worker_task
        await manager.shutdown()

    asyncio.run(exercise())


@pytest.mark.parametrize("terminal_status", ["submitted_pending_confirmation", "unknown"])
def test_explicit_delete_removes_indeterminate_submission_without_lifecycle_reset(
    repository, terminal_status
):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, terminal_status, error="submission outcome is unknown")

    def unexpected_lifecycle(*args, **kwargs):
        raise AssertionError("indeterminate deletion must not reset task lifecycle")

    repo.set_task_lifecycle = unexpected_lifecycle

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        await manager.delete(record.id)

    asyncio.run(exercise())
    assert repo.get_task(record.id) is None


def test_update_rejects_task_with_active_worker_without_mutating(repository):
    repo, settings = repository
    record = repo.create_task(task_data())

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=BlockingWorker)
        await manager.start(record.id)
        with pytest.raises(RuntimeError, match="owned"):
            await manager.update(record.id, TaskUpdate(target_price=70))
        assert repo.get_task(record.id).target_price == 59
        await manager.stop(record.id)
        updated = await manager.update(record.id, TaskUpdate(target_price=70))
        await manager.shutdown()
        return updated

    updated = asyncio.run(exercise())
    assert updated.target_price == 70


@pytest.mark.parametrize("active_status", ["running", "checking", "ordering"])
def test_update_rejects_persisted_active_task_without_worker_handle(repository, active_status):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_status(record.id, active_status)

    async def exercise():
        manager = TaskManager(repo, settings=settings)
        with pytest.raises(RuntimeError, match=active_status):
            await manager.update(record.id, TaskUpdate(target_price=70))

    asyncio.run(exercise())

    current = repo.get_task(record.id)
    assert current.status == active_status
    assert current.target_price == 59


def test_update_rejects_task_with_retained_timeout_worker(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    release = threading.Event()

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=lambda task, stop_event, pause_event: NonCooperativeWorker(
                task, stop_event, pause_event, release
            ),
            stop_timeout=0.02,
        )
        await manager.start(record.id)
        await wait_until(lambda: manager.owned_worker_count() == 1)
        with pytest.raises(RuntimeError, match="did not stop"):
            await manager.stop(record.id)
        with pytest.raises(RuntimeError, match="owned"):
            await manager.update(record.id, TaskUpdate(target_price=70))
        release.set()
        await manager._workers[record.id].worker_task
        return await manager.update(record.id, TaskUpdate(target_price=70))

    updated = asyncio.run(exercise())
    assert updated.target_price == 70


def test_single_check_worker_uses_real_client_boundary(repository):
    repo, _ = repository
    record = repo.create_task(task_data())
    calls = []

    class FakeClient:
        def check_stock(self, goods_id):
            calls.append(("check_stock", goods_id))
            return True

        def close(self):
            calls.append(("close",))

    worker = SingleCheckWorker(
        record,
        client_factory=FakeClient,
        repository=repo,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
    )

    worker.run()

    result = repo.get_task(record.id)
    assert calls == [("check_stock", "418"), ("close",)]
    assert result.status == "stopped"
    assert result.last_stock_status == "available"


def test_unexpected_worker_exception_persists_redacted_failure(repository):
    repo, settings = repository
    record = repo.create_task(task_data())

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=lambda task, stop_event, pause_event: RaisingWorker(
                task, stop_event, pause_event
            ),
        )
        await manager.start(record.id)
        await wait_until(lambda: record.id not in manager._workers)
        return repo.get_task(record.id)

    result = asyncio.run(exercise())

    assert result.status == "failed"
    assert "worker-secret" not in result.last_error
    assert "worker-token" not in result.last_error
    assert result.running_before_shutdown is False


def test_pause_resume_and_stop_use_single_owned_worker(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        await manager.start(record.id)
        paused = await manager.pause(record.id)
        resumed = await manager.resume(record.id)
        stopped = await manager.stop(record.id)
        await manager.shutdown()
        return paused, resumed, stopped

    paused, resumed, stopped = asyncio.run(exercise())

    assert paused["status"] == "paused"
    assert resumed["status"] == "running"
    assert stopped["status"] == "stopped"
    assert len(created) == 2


def test_stale_active_states_are_stopped_and_success_is_not_started(repository):
    repo, settings = repository
    stale = repo.create_task(task_data())
    success = repo.create_task(task_data(password="second"))
    repo.set_task_status(stale.id, "checking")
    repo.set_task_status(success.id, "success")
    created = []

    def worker_factory(task, stop_event, pause_event):
        created.append(task.id)
        return BlockingWorker(task, stop_event, pause_event)

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        recovered = await manager.recover_stale_tasks()
        await manager.shutdown()
        return recovered

    recovered = asyncio.run(exercise())

    assert recovered == 1
    assert repo.get_task(stale.id).status == "stopped"
    assert repo.get_task(success.id).status == "success"
    assert created == []


def test_marked_active_task_is_restarted_during_recovery(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    repo.set_task_lifecycle(record.id, "checking", running_before_shutdown=True)
    created = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        recovered = await manager.recover_stale_tasks()
        await wait_until(lambda: len(created) == 1)
        await manager.stop(record.id)
        await manager.shutdown()
        return recovered

    assert asyncio.run(exercise()) == 1
    assert len(created) == 1


def test_shutdown_stops_and_awaits_each_worker_once(repository):
    repo, settings = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="second"))
    workers = []

    def worker_factory(task, stop_event, pause_event):
        worker = BlockingWorker(task, stop_event, pause_event)
        workers.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=worker_factory)
        await manager.start(first.id)
        await manager.start(second.id)
        await manager.shutdown()
        await manager.shutdown()

    asyncio.run(exercise())

    assert len(workers) == 2
    assert all(worker.run_count == 1 for worker in workers)
    assert repo.get_task(first.id).status == "stopped"
    assert repo.get_task(second.id).status == "stopped"


def test_start_is_rejected_after_shutdown(repository):
    repo, settings = repository
    record = repo.create_task(task_data())

    async def exercise():
        manager = TaskManager(repo, settings=settings, worker_factory=BlockingWorker)
        await manager.shutdown()
        with pytest.raises(RuntimeError, match="shut down"):
            await manager.start(record.id)

    asyncio.run(exercise())


def test_check_now_is_one_shot_and_does_not_start_monitor(repository):
    repo, settings = repository
    record = repo.create_task(task_data())
    calls = []
    created = []

    def check_factory(task, stop_event, pause_event):
        worker = OneShotWorker(task, stop_event, pause_event, calls)
        created.append(worker)
        return worker

    async def exercise():
        manager = TaskManager(
            repo,
            settings=settings,
            worker_factory=lambda task, stop_event, pause_event: BlockingWorker(
                task, stop_event, pause_event
            ),
            check_factory=check_factory,
        )
        result = await manager.check_now(record.id)
        await wait_until(lambda: record.id not in manager._workers)
        return result

    result = asyncio.run(exercise())

    assert result["started"] is True
    assert calls == [record.id]
    assert len(created) == 1
    assert repo.get_task(record.id).status == "stopped"


def test_api_contract_masks_secrets_and_protects_routes(repository):
    repo, settings = repository
    app = create_app(settings=settings)
    task_id = None

    async def exercise():
        nonlocal task_id
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                public = await client.get("/api/health")
                unauthorized = await client.get("/api/tasks")
                headers = {"X-API-Key": "test-api-key"}
                invalid = await client.post(
                    "/api/tasks",
                    headers=headers,
                    json={
                        "goods_id": "not-a-number",
                        "target_price": 0,
                        "wait_interval": 1,
                        "email": "not-an-email",
                        "password": "",
                    },
                )
                created = await client.post(
                    "/api/tasks",
                    headers=headers,
                    json={
                        "goods_id": "418",
                        "target_price": 59,
                        "wait_interval": 5,
                        "email": "buyer@example.com",
                        "password": "plain-password",
                    },
                )
                task_id = created.json()["id"]
                app.state.repository.create_order(
                    task_id, "failed", "72.00", "checkout failed"
                )
                app.state.repository.append_log("ERROR", task_id, "checkout failed")
                app.state.repository.set_task_status(
                    task_id, "failed", error="checkout failed"
                )
                fetched = await client.get(f"/api/tasks/{task_id}", headers=headers)
                updated = await client.put(
                    f"/api/tasks/{task_id}",
                    headers=headers,
                    json={"password": "replacement", "target_price": 61},
                )
                history = await client.get(
                    f"/api/tasks/{task_id}/history", headers=headers
                )
                orders = await client.get("/api/orders", headers=headers)
                filtered_orders = await client.get(
                    "/api/orders?task_id=" + task_id + "&status=failed&limit=1",
                    headers=headers,
                )
                logs = await client.get("/api/logs", headers=headers)
                filtered_logs = await client.get(
                    "/api/logs?task_id=" + task_id + "&level=ERROR&limit=1",
                    headers=headers,
                )
                stats = await client.get("/api/stats", headers=headers)
                settings_response = await client.get("/api/settings", headers=headers)
                settings_updated = await client.put(
                    "/api/settings",
                    headers=headers,
                    json={"log_level": "DEBUG", "telegram_enabled": True},
                )
                settings_invalid = await client.put(
                    "/api/settings",
                    headers=headers,
                    json={"log_level": "TRACE"},
                )
                settings_after_invalid = await client.get(
                    "/api/settings", headers=headers
                )
                null_url = await client.put(
                    f"/api/tasks/{task_id}",
                    headers=headers,
                    json={"stock_url": None},
                )
                cleared_orders = await client.delete("/api/orders", headers=headers)
                cleared_logs = await client.delete("/api/logs", headers=headers)
                missing = await client.get("/api/tasks/missing", headers=headers)
                deleted = await client.delete(f"/api/tasks/{task_id}", headers=headers)
        return (
                public,
                unauthorized,
                invalid,
                created,
            fetched,
            updated,
            history,
                orders,
                filtered_orders,
                logs,
                filtered_logs,
                stats,
                settings_response,
                settings_updated,
                settings_invalid,
                settings_after_invalid,
                null_url,
                cleared_orders,
                cleared_logs,
                missing,
            deleted,
        )

    responses = asyncio.run(exercise())
    (
        public,
        unauthorized,
        invalid,
        created,
        fetched,
        updated,
        history,
        orders,
        filtered_orders,
        logs,
        filtered_logs,
        stats,
        settings_response,
        settings_updated,
        settings_invalid,
        settings_after_invalid,
        null_url,
        cleared_orders,
        cleared_logs,
        missing,
        deleted,
    ) = responses

    assert public.status_code == 200
    assert unauthorized.status_code == 401
    assert invalid.status_code == 422
    assert created.status_code == 201
    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert history.status_code == 200
    assert orders.status_code == 200
    assert filtered_orders.status_code == 200
    assert len(filtered_orders.json()) == 1
    assert logs.status_code == 200
    assert len(logs.json()) == 1
    assert filtered_logs.status_code == 200
    assert len(filtered_logs.json()) == 1
    assert history.json()[0]["status"] == "failed"
    assert stats.status_code == 200
    assert stats.json()["failure_count"] == 1
    assert settings_response.status_code == 200
    assert settings_updated.status_code == 200
    assert settings_updated.json()["log_level"] == "DEBUG"
    assert settings_invalid.status_code == 422
    assert settings_after_invalid.json()["log_level"] == "DEBUG"
    assert null_url.status_code == 422
    assert cleared_orders.status_code == 204
    assert cleared_logs.status_code == 204
    assert missing.status_code == 404
    assert deleted.status_code == 204
    assert "plain-password" not in created.text
    assert "password_ciphertext" not in created.text
    assert "replacement" not in updated.text
    assert "test-api-key" not in settings_response.text
    assert settings.data_encryption_key not in settings_response.text


def test_lifecycle_endpoints_return_conflicts_for_owned_worker(repository):
    repo, settings = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"X-API-Key": "test-api-key"}
                created = await client.post(
                    "/api/tasks",
                    headers=headers,
                    json={
                        "goods_id": "418",
                        "target_price": 59,
                        "wait_interval": 5,
                        "email": "buyer@example.com",
                        "password": "plain-password",
                    },
                )
                task_id = created.json()["id"]
                started = await client.post(
                    f"/api/tasks/{task_id}/start", headers=headers
                )
                active_update = await client.put(
                    f"/api/tasks/{task_id}",
                    headers=headers,
                    json={"target_price": 60},
                )
                checked = await client.post(
                    f"/api/tasks/{task_id}/check", headers=headers
                )
                stopped = await client.post(
                    f"/api/tasks/{task_id}/stop", headers=headers
                )
                app.state.repository.set_task_status(
                    task_id, "submitted_pending_confirmation", error="unknown"
                )
                indeterminate_stop = await client.post(
                    f"/api/tasks/{task_id}/stop", headers=headers
                )
                indeterminate_start = await client.post(
                    f"/api/tasks/{task_id}/start", headers=headers
                )
                indeterminate_check = await client.post(
                    f"/api/tasks/{task_id}/check", headers=headers
                )
                indeterminate_task = await client.get(
                    f"/api/tasks/{task_id}", headers=headers
                )
        return (
            started,
            active_update,
            checked,
            stopped,
            indeterminate_stop,
            indeterminate_start,
            indeterminate_check,
            indeterminate_task,
        )

    app.state.worker_factory = lambda task, stop_event, pause_event: BlockingWorker(
        task, stop_event, pause_event
    )
    (
        started,
        active_update,
        checked,
        stopped,
        indeterminate_stop,
        indeterminate_start,
        indeterminate_check,
        indeterminate_task,
    ) = asyncio.run(exercise())

    assert started.status_code == 200
    assert active_update.status_code == 409
    assert checked.status_code == 409
    assert stopped.status_code == 200
    assert indeterminate_stop.status_code == 409
    assert indeterminate_start.status_code == 409
    assert indeterminate_check.status_code == 409
    assert indeterminate_task.json()["status"] == "submitted_pending_confirmation"


def test_importing_main_does_not_create_a_manager_or_worker():
    from backend.app.main import app

    assert not hasattr(app.state, "manager")
