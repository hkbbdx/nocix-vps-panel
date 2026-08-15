import asyncio
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
import pytest
from selenium.common import exceptions
from selenium.webdriver.common.by import By

from nocix_fucker.client import Client
from backend.app.config import Settings
from backend.app.manager import TaskManager
from backend.app.main import create_app


class FakeElement:
    def __init__(self, driver, kind, value="", text="", visible=True, form_owner=None):
        self.driver = driver
        self.kind = kind
        self.value = value
        self.text = text
        self.visible = visible
        self.form_owner = form_owner
        self.clear_count = 0

    def is_displayed(self):
        return self.visible

    def find_elements(self, by, value):
        if by == By.XPATH and value == "ancestor::form[1]" and self.form_owner:
            return [self.form_owner]
        return []

    def get_attribute(self, name):
        if name == "value":
            return self.value
        return None

    def clear(self):
        self.clear_count += 1
        self.value = ""

    def send_keys(self, value):
        self.value += value

    def click(self):
        if self.kind == "login_submit":
            self.driver.submit_login()
        elif self.kind == "code_submit":
            self.driver.submit_code(self.driver.code_field.value)


class FakeForm(FakeElement):
    def __init__(self, driver, fields, submit):
        super().__init__(driver, "form")
        self.fields = fields
        self.submit = submit
        for field in fields.values():
            field.form_owner = self
        submit.form_owner = self

    def find_elements(self, by, value):
        if by == By.NAME:
            return [self.fields[value]] if value in self.fields else []
        if by == By.XPATH and value == "ancestor::form[1]":
            return [self]
        if by == By.CLASS_NAME and value == "hvr-sweep-to-right":
            return [self.submit]
        if by == By.CSS_SELECTOR and value in {
            "button[type='submit']",
            "input[type='submit']",
        }:
            return [self.submit]
        return []


class FakeDriver:
    def __init__(self, final_state="checkout", expected_code="246810"):
        self.state = "first_login"
        self.final_state = final_state
        self.expected_code = expected_code
        self.submissions = []
        self.code_attempts = []
        self.login_submit_count = 0
        self.last_code_field = None
        self.current_url = "https://example.test/checkout"
        self.forms = {}
        for state in ("first_login", "second_login"):
            fields = {
                "existing_username": FakeElement(self, f"{state}_email"),
                "existing_password": FakeElement(self, f"{state}_password"),
            }
            self.forms[state] = FakeForm(
                self,
                fields,
                FakeElement(self, kind="login_submit"),
            )
        self.code_field = FakeElement(self, "code_field")

    def find_elements(self, by, value):
        if by == By.TAG_NAME and value == "form":
            if self.state in {"first_login", "second_login"}:
                return [self.forms[self.state]]
            return []

        if by == By.CSS_SELECTOR and value in {
            "input[name='email_code']",
            "input[name='verification_code']",
            "input[name='code']",
            "input[autocomplete='one-time-code']",
        }:
            if self.state == "code":
                self.last_code_field = self.code_field
                return [self.last_code_field]
            return []

        if by == By.CSS_SELECTOR and value in {
            "button[type='submit']",
            "input[type='submit']",
            ".email-code-submit",
        }:
            if self.state == "code":
                return [FakeElement(self, "code_submit")]
            return []

        if by == By.TAG_NAME and value == "body":
            page_text = {
                "code": "Enter the verification code sent to your email.",
                "checkout": "Checkout details",
            }.get(self.state, "Login")
            return [FakeElement(self, "body", text=page_text)]

        return []

    def submit_login(self):
        credentials = self._visible_credentials()
        self.submissions.append(
            (credentials["existing_username"].value, credentials["existing_password"].value)
        )
        self.login_submit_count += 1
        if self.login_submit_count == 1:
            self.state = "second_login"
        else:
            self.state = self.final_state

    def submit_code(self, code):
        self.code_attempts.append(code)
        if code == self.expected_code:
            self.state = "checkout"

    def _visible_credentials(self):
        return self.forms[self.state].fields


class MarkerOnlyDriver:
    def __init__(self, marker_visible=True, code_visible=False, body_text=""):
        self.marker = FakeElement(self, "marker", visible=marker_visible)
        self.code = FakeElement(self, "code", visible=code_visible)
        self.body = FakeElement(self, "body", text=body_text)

    def find_elements(self, by, value):
        if by == By.CSS_SELECTOR and value == "[data-testid='email-code']":
            return [self.marker]
        if by == By.CSS_SELECTOR and value.startswith("input["):
            return [self.code]
        if by == By.ID and value in {"email_code", "verification_code", "email-code-form"}:
            return [self.code if value != "email-code-form" else self.marker]
        if by == By.TAG_NAME and value == "body":
            return [self.body]
        return []


class MixedContainer(FakeElement):
    def __init__(self, driver):
        super().__init__(driver, "common-container")

    def find_elements(self, by, value):
        if by == By.NAME and value == "existing_username":
            return [self.driver.fields["email"]]
        if by == By.NAME and value == "existing_password":
            return [self.driver.fields["password"]]
        if by == By.CLASS_NAME and value == "hvr-sweep-to-right":
            return [self.driver.fields["submit"]]
        return []


class MixedFormDriver:
    def __init__(self):
        self.email_form = object()
        self.password_form = object()
        self.submit_form = object()
        self.fields = {
            "email": FakeElement(self, "email", form_owner=self.email_form),
            "password": FakeElement(self, "password", form_owner=self.password_form),
            "submit": FakeElement(
                self, "submit", form_owner=self.submit_form
            ),
        }
        self.container = MixedContainer(self)

    def find_elements(self, by, value):
        if by == By.XPATH:
            return [self.container]
        return []
class FakeWait:
    def __init__(self, driver, attempts=3):
        self.driver = driver
        self.attempts = attempts

    def until(self, condition):
        for _ in range(self.attempts):
            result = condition(self.driver)
            if result:
                return result
        raise exceptions.TimeoutException()


def build_client(driver):
    client = Client.__new__(Client)
    client._driver = driver
    client._wait = FakeWait(driver)
    return client


def test_existing_login_submits_credentials_twice():
    driver = FakeDriver()
    client = build_client(driver)

    assert client.login_existing_customer("person@example.test", "correct horse") is True
    assert driver.submissions == [
        ("person@example.test", "correct horse"),
        ("person@example.test", "correct horse"),
    ]
    assert driver.login_submit_count == 2


def test_second_login_uses_fresh_visible_form_fields():
    driver = FakeDriver()
    client = build_client(driver)
    first_form = driver.forms["first_login"]
    second_form = driver.forms["second_login"]

    assert client.login_existing_customer("person@example.test", "correct horse") is True
    assert first_form.fields["existing_username"].value == "person@example.test"
    assert first_form.fields["existing_password"].value == "correct horse"
    assert second_form.fields["existing_username"].value == "person@example.test"
    assert second_form.fields["existing_password"].value == "correct horse"
    assert first_form.fields["existing_username"] is not second_form.fields["existing_username"]
    assert first_form.fields["existing_password"] is not second_form.fields["existing_password"]


def test_mixed_form_controls_are_rejected():
    client = build_client(MixedFormDriver())

    assert client._visible_login_form() is None


def test_second_login_detects_email_code_page():
    driver = FakeDriver(final_state="code")
    client = build_client(driver)

    assert client.login_existing_customer("person@example.test", "correct horse") is True
    assert client.is_email_code_required() is True


def test_login_without_code_page_continues():
    client = build_client(FakeDriver(final_state="checkout"))

    assert client.login_existing_customer("person@example.test", "correct horse") is True
    assert client.is_email_code_required() is False


def test_visible_code_marker_requires_no_code_field():
    client = build_client(MarkerOnlyDriver(marker_visible=True, body_text="Checkout"))

    assert client.is_email_code_required() is True


def test_hidden_code_field_is_ignored():
    client = build_client(
        MarkerOnlyDriver(marker_visible=False, code_visible=False, body_text="Checkout")
    )

    assert client.is_email_code_required() is False


def test_hidden_code_marker_is_ignored_on_no_code_page():
    client = build_client(
        MarkerOnlyDriver(marker_visible=False, code_visible=False, body_text="Checkout")
    )

    assert client.is_email_code_required() is False


def test_email_code_acceptance_submits_visible_code_form():
    driver = FakeDriver(final_state="code")
    client = build_client(driver)
    client.login_existing_customer("person@example.test", "correct horse")

    assert client.submit_email_code("246810") is True
    assert driver.code_attempts == ["246810"]
    assert client.is_email_code_required() is False


def test_email_code_rejection_clears_field_and_keeps_waiting():
    driver = FakeDriver(final_state="code")
    client = build_client(driver)
    client.login_existing_customer("person@example.test", "correct horse")

    assert client.submit_email_code("135790") is False
    assert driver.code_attempts == ["135790"]
    assert driver.last_code_field.clear_count >= 1
    assert driver.last_code_field.value == ""
    assert client.is_email_code_required() is True


@pytest.mark.parametrize("code", ["", "123", "1234567890123", "12a4", "１２３４"])
def test_invalid_email_code_is_rejected_at_client_boundary(code):
    driver = FakeDriver(final_state="code")
    client = build_client(driver)
    client.login_existing_customer("person@example.test", "correct horse")

    assert client.submit_email_code(code) is False
    assert driver.code_attempts == []


def test_login_errors_do_not_leak_password_or_code(monkeypatch):
    messages = []
    monkeypatch.setattr("nocix_fucker.client.logger.debug", messages.append)
    monkeypatch.setattr("nocix_fucker.client.logger.trace", messages.append)

    driver = FakeDriver(final_state="code")
    client = build_client(driver)
    password = "password-never-log"
    code = "135790"

    assert client.login_existing_customer("person@example.test", password) is True
    assert client.submit_email_code(code) is False
    output = " ".join(messages)
    assert password not in output
    assert code not in output


@dataclass
class CoordinatorTask:
    id: str = "login-task"
    goods_id: str = "418"
    stock_url: str | None = None
    cart_url: str | None = None
    target_price: float = 59.0
    wait_interval: float = 5.0
    operating_system: str = "debian"
    email: str = "person@example.test"
    new_customer: bool = False
    payment_method: str = "paypal"
    auto_submit: bool = True
    status: str = "stopped"
    last_error: str | None = None
    running_before_shutdown: bool = False


@dataclass
class CoordinatorRepository:
    task: CoordinatorTask
    statuses: list[tuple] = field(default_factory=list)
    orders: list[tuple] = field(default_factory=list)
    logs: list[tuple] = field(default_factory=list)

    def get_task(self, task_id):
        return self.task if task_id == self.task.id else None

    def get_decrypted_password(self, task_id):
        return "password-never-log"

    def set_task_lifecycle(self, task_id, status, *, running_before_shutdown, error=None):
        self.task.status = status
        self.task.last_error = error
        self.task.running_before_shutdown = running_before_shutdown
        self.statuses.append((task_id, status, error))
        return self.task

    def set_task_status(self, task_id, status, error=None):
        self.task.status = status
        self.task.last_error = error
        self.statuses.append((task_id, status, error))
        return self.task

    def set_running_before_shutdown(self, task_id, value):
        self.task.running_before_shutdown = value
        return self.task

    def set_stock_check_result(self, task_id, stock_status):
        return self.task

    def create_order(self, task_id, status, observed_price=None, error=None):
        self.orders.append((task_id, status, observed_price, error))

    def append_log(self, level, task_id, message):
        self.logs.append((level, task_id, message))


class CoordinatorClient:
    current_url = "https://nocix.net/cart/?id=418"
    last_price_text = None

    def __init__(self):
        self.calls = []
        self.code_required = True
        self.codes = []
        self.closed = False

    def check_stock(self, goods_id, stock_url=None):
        self.calls.append(("check_stock", goods_id))
        return True

    def open_cart(self, goods_id, cart_url=None):
        self.calls.append(("open_cart", goods_id))

    def login_existing_customer(self, email, password):
        self.calls.append(("login_existing_customer", email, password))
        return True

    def is_email_code_required(self):
        return self.code_required

    def submit_email_code(self, code):
        self.codes.append(code)
        self.calls.append(("submit_email_code",))
        if code == "246810":
            self.code_required = False
            return True
        return False

    def select_operating_system(self, value):
        self.calls.append(("select_operating_system", value))
        return True

    def match_price(self, target_price):
        self.calls.append(("match_price", target_price))
        return True

    def fill_in_customer_info(self, **kwargs):
        self.calls.append(("fill_in_customer_info", kwargs))

    def fill_in_payment_info(self, **kwargs):
        self.calls.append(("fill_in_payment_info", kwargs))

    def click_next_step_button(self):
        self.calls.append(("click_next_step_button",))

    def submit_order(self):
        self.calls.append(("submit_order",))
        return None

    def close(self):
        self.closed = True


class BlockingCoordinatorClient(CoordinatorClient):
    def __init__(self):
        super().__init__()
        self.code_started = threading.Event()
        self.release_code = threading.Event()

    def submit_email_code(self, code):
        self.codes.append(code)
        self.calls.append(("submit_email_code",))
        self.code_started.set()
        self.release_code.wait(timeout=2.0)
        if code == "246810":
            self.code_required = False
            return True
        return False


def wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        time.sleep(0.005)


def test_manager_waits_for_code_and_resumes_same_client_session():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()

    def worker_factory(task, stop_event, pause_event):
        from backend.app.worker import CheckoutWorker

        return CheckoutWorker(
            task,
            client_factory=lambda: client,
            repository=repository,
            stop_event=stop_event,
            pause_event=pause_event,
            verification_timeout=1.0,
        )

    async def exercise():
        manager = TaskManager(repository, worker_factory=worker_factory)
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        state = manager.get_login_state(task.id)
        assert state["task_id"] == task.id
        assert state["status"] == "waiting_for_email_code"
        assert state["waiting"] is True
        assert "code" not in state
        assert "password" not in state
        result = manager.submit_email_code(task.id, "246810")
        assert result["accepted"] is True
        await manager._workers[task.id].worker_task
        return manager

    manager = asyncio.run(exercise())

    assert task.status == "success"
    assert client.codes == ["246810"]
    assert client.closed is True
    assert [call[0] for call in client.calls].count("login_existing_customer") == 1
    assert [status[1] for status in repository.statuses] == [
        "running",
        "checking",
        "ordering",
        "login_first",
        "login_second",
        "waiting_for_email_code",
        "ordering",
        "success",
    ]
    assert repository.orders == [(task.id, "success", None, None)]
    assert manager.owned_worker_count() == 0


def test_second_code_is_rejected_while_first_submission_is_in_flight():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = BlockingCoordinatorClient()

    async def exercise():
        manager = build_coordinator_manager(task, repository, client)
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        worker = manager._workers[task.id].worker
        assert manager.submit_email_code(task.id, "246810")["accepted"] is True
        await asyncio.to_thread(wait_for, client.code_started.is_set)
        conflict = manager.submit_email_code(task.id, "135790")
        assert worker._verification.pending_code is None
        assert worker._verification.attempt_in_flight is True
        client.release_code.set()
        await manager._workers[task.id].worker_task
        return conflict, worker

    conflict, worker = asyncio.run(exercise())

    assert conflict == {
        "accepted": False,
        "status": "waiting_for_email_code",
        "message": "verification attempt already in flight",
    }
    assert client.codes == ["246810"]
    assert repository.orders[-1][1] == "success"
    assert worker._verification.pending_code is None
    assert worker._verification.attempt_in_flight is False
    assert client.closed is True


def test_cancel_during_code_submission_wins_before_checkout():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = BlockingCoordinatorClient()

    async def exercise():
        manager = build_coordinator_manager(task, repository, client)
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        worker = manager._workers[task.id].worker
        assert manager.submit_email_code(task.id, "246810")["accepted"] is True
        await asyncio.to_thread(wait_for, client.code_started.is_set)
        cancelled = manager.cancel_login(task.id)
        client.release_code.set()
        await manager._workers[task.id].worker_task
        return cancelled, worker

    cancelled, worker = asyncio.run(exercise())

    assert cancelled == {
        "accepted": True,
        "status": "waiting_for_email_code",
        "message": "verification cancelled",
    }
    assert task.status == "failed"
    assert repository.orders == []
    assert not any(call[0] in {"select_operating_system", "submit_order"} for call in client.calls)
    assert worker._verification.pending_code is None
    assert worker._verification.attempt_in_flight is False
    assert client.closed is True


def test_cancel_after_client_accept_before_finalization_prevents_checkout():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()

    async def exercise():
        manager = build_coordinator_manager(task, repository, client)
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        worker = manager._workers[task.id].worker
        original_finalize = worker._verification.finalize_attempt

        def cancel_before_finalize(accepted, now, stopped, paused):
            worker.cancel_verification()
            return original_finalize(accepted, now, stopped, paused)

        worker._verification.finalize_attempt = cancel_before_finalize
        assert manager.submit_email_code(task.id, "246810")["accepted"] is True
        await manager._workers[task.id].worker_task
        return worker

    worker = asyncio.run(exercise())

    assert task.status == "failed"
    assert repository.orders == []
    assert not any(call[0] in {"select_operating_system", "submit_order"} for call in client.calls)
    assert worker._verification.pending_code is None
    assert worker._verification.attempt_in_flight is False
    assert client.closed is True


def test_code_woken_before_deadline_is_rejected_if_consumption_is_delayed():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()
    now = [0.0]

    async def exercise():
        manager = build_coordinator_manager(
            task,
            repository,
            client,
            verification_timeout=5.0,
            clock=lambda: now[0],
        )
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        worker = manager._workers[task.id].worker
        original_consume = worker._verification.consume

        def delayed_consume(_clock):
            now[0] = 5.0
            return original_consume(now[0])

        worker._verification.consume = delayed_consume
        assert manager.submit_email_code(task.id, "246810")["accepted"] is True
        await manager._workers[task.id].worker_task
        return worker

    worker = asyncio.run(exercise())

    assert task.status == "failed"
    assert repository.orders == []
    assert client.codes == []
    assert worker._verification.pending_code is None
    assert worker._verification.attempt_in_flight is False
    assert client.closed is True


def test_login_failure_is_pre_order_and_uses_generic_error():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()

    def login_failure(email, password):
        client.calls.append(("login_existing_customer", email, password))
        return False

    client.login_existing_customer = login_failure
    client.code_required = False
    notifications = []

    from backend.app.worker import CheckoutWorker

    worker = CheckoutWorker(
        task,
        client_factory=lambda: client,
        repository=repository,
        notifier=notifications.append,
    )
    worker.run()

    assert task.status == "failed"
    assert repository.orders == []
    assert repository.statuses[-1][2] == "login failed"
    assert all("password-never-log" not in repr(item) for item in repository.statuses)
    assert all("password-never-log" not in item for item in repository.logs)
    assert all("password-never-log" not in item for item in notifications)


def test_no_code_page_continues_after_login_without_waiting():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()
    client.code_required = False

    from backend.app.worker import CheckoutWorker

    CheckoutWorker(
        task,
        client_factory=lambda: client,
        repository=repository,
    ).run()

    assert task.status == "success"
    assert "waiting_for_email_code" not in [status[1] for status in repository.statuses]
    assert client.codes == []


def build_coordinator_manager(
    task,
    repository,
    client,
    *,
    verification_timeout=1.0,
    notifications=None,
    clock=time.monotonic,
):
    def worker_factory(task, stop_event, pause_event):
        from backend.app.worker import CheckoutWorker

        return CheckoutWorker(
            task,
            client_factory=lambda: client,
            repository=repository,
            stop_event=stop_event,
            pause_event=pause_event,
            notifier=(notifications.append if notifications is not None else None),
            verification_timeout=verification_timeout,
            clock=clock,
        )

    return TaskManager(repository, worker_factory=worker_factory)


def test_wrong_code_is_cleared_and_retry_remains_on_same_worker():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()
    notifications = []

    async def exercise():
        manager = build_coordinator_manager(
            task, repository, client, notifications=notifications
        )
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        assert manager.submit_email_code(task.id, "135790")["accepted"] is True
        await asyncio.to_thread(wait_for, lambda: client.codes == ["135790"])
        state = manager.get_login_state(task.id)
        assert state["waiting"] is True
        assert state["attempts"] == 1
        assert state["last_error"] == "email verification failed"
        assert manager.submit_email_code(task.id, "246810")["accepted"] is True
        await manager._workers[task.id].worker_task

    asyncio.run(exercise())

    assert client.codes == ["135790", "246810"]
    assert repository.orders[-1][1] == "success"
    assert all("135790" not in repr(item) for item in repository.logs)
    assert all("135790" not in item for item in notifications)


def test_invalid_code_and_unowned_task_are_safe_conflicts_without_state_change():
    task = CoordinatorTask()
    repository = CoordinatorRepository(task)
    client = CoordinatorClient()

    async def exercise():
        manager = build_coordinator_manager(task, repository, client)
        await manager.start(task.id)
        await asyncio.to_thread(wait_for, lambda: task.status == "waiting_for_email_code")
        before = manager.get_login_state(task.id)
        invalid = manager.submit_email_code(task.id, "12a4")
        after = manager.get_login_state(task.id)
        with pytest.raises(KeyError):
            manager.get_login_state("missing")
        manager._workers[task.id].worker.cancel_verification()
        await manager._workers[task.id].worker_task
        return manager, before, invalid, after

    manager, before, invalid, after = asyncio.run(exercise())
    assert invalid == {
        "accepted": False,
        "status": "waiting_for_email_code",
        "message": "invalid verification code",
    }
    assert after == before


def test_cancel_and_timeout_fail_without_order_or_code_persistence():
    cancelled_task = CoordinatorTask(id="cancelled")
    cancelled_repo = CoordinatorRepository(cancelled_task)
    cancelled_client = CoordinatorClient()

    async def cancel_exercise():
        manager = build_coordinator_manager(
            cancelled_task, cancelled_repo, cancelled_client
        )
        await manager.start(cancelled_task.id)
        await asyncio.to_thread(
            wait_for, lambda: cancelled_task.status == "waiting_for_email_code"
        )
        result = manager.cancel_login(cancelled_task.id)
        await manager._workers[cancelled_task.id].worker_task
        return result, manager

    cancel_result, cancel_manager = asyncio.run(cancel_exercise())
    assert cancel_result["accepted"] is True
    assert cancelled_task.status == "failed"
    assert cancelled_repo.orders == []
    assert cancelled_task.last_error == "verification cancelled"
    assert cancel_manager.owned_worker_count() == 0

    timeout_task = CoordinatorTask(id="timeout")
    timeout_repo = CoordinatorRepository(timeout_task)
    timeout_client = CoordinatorClient()

    async def timeout_exercise():
        manager = build_coordinator_manager(
            timeout_task,
            timeout_repo,
            timeout_client,
            verification_timeout=0.02,
        )
        await manager.start(timeout_task.id)
        await manager._workers[timeout_task.id].worker_task

    asyncio.run(timeout_exercise())
    assert timeout_task.status == "failed"
    assert timeout_repo.orders == []
    assert timeout_client.closed is True


@dataclass
class ApiLoginTask:
    id: str = "api-task"


class ApiLoginRepository:
    def __init__(self, task_id="api-task"):
        self.task = ApiLoginTask(task_id)

    def get_task(self, task_id):
        return self.task if task_id == self.task.id else None


class ApiLoginManager:
    def __init__(self, task_id="api-task", *, waiting=True):
        self.repository = ApiLoginRepository(task_id)
        self.codes = []
        self.worker_creations = 0
        self.state = {
            "task_id": task_id,
            "status": "waiting_for_email_code" if waiting else "stopped",
            "waiting": waiting,
            "attempts": 0,
            "remaining_seconds": 120 if waiting else 0,
            "last_error": None,
        }

    def get_login_state(self, task_id):
        if self.repository.get_task(task_id) is None:
            raise KeyError(task_id)
        return dict(self.state)

    def submit_email_code(self, task_id, code):
        state = self.get_login_state(task_id)
        if not state["waiting"]:
            return {"accepted": False, "status": state["status"]}
        self.codes.append(code)
        self.state.update(
            status="ordering",
            waiting=False,
            remaining_seconds=0,
            last_error=None,
        )
        return {"accepted": True, "status": "ordering"}

    def cancel_login(self, task_id):
        state = self.get_login_state(task_id)
        if not state["waiting"]:
            return {"accepted": False, "status": state["status"]}
        self.state.update(
            status="failed",
            waiting=False,
            remaining_seconds=0,
            last_error="verification cancelled",
        )
        return {"accepted": True, "status": "failed"}


def build_login_api(manager):
    app = create_app(settings=Settings(api_key="api-test-key"))
    app.state.manager = manager
    return app


async def login_request(app, method, path, *, headers=None, json=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, headers=headers, json=json)


def test_login_api_requires_api_key_for_every_endpoint():
    app = build_login_api(ApiLoginManager())

    async def exercise():
        return await asyncio.gather(
            login_request(app, "GET", "/api/tasks/api-task/login-state"),
            login_request(app, "POST", "/api/tasks/api-task/email-code", json={"code": "1234"}),
            login_request(app, "POST", "/api/tasks/api-task/login-cancel"),
        )

    responses = asyncio.run(exercise())
    assert [response.status_code for response in responses] == [401, 401, 401]


def test_login_state_returns_only_public_waiting_state():
    app = build_login_api(ApiLoginManager())
    response = asyncio.run(
        login_request(
            app,
            "GET",
            "/api/tasks/api-task/login-state",
            headers={"X-API-Key": "api-test-key"},
        )
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "api-task",
        "status": "waiting_for_email_code",
        "waiting": True,
        "attempts": 0,
        "remaining_seconds": 120,
        "last_error": None,
    }


def test_valid_email_code_submits_to_existing_manager_without_creating_worker():
    manager = ApiLoginManager()
    app = build_login_api(manager)
    response = asyncio.run(
        login_request(
            app,
            "POST",
            "/api/tasks/api-task/email-code",
            headers={"X-API-Key": "api-test-key"},
            json={"code": "246810"},
        )
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "api-task",
        "status": "ordering",
        "waiting": False,
        "attempts": 0,
        "remaining_seconds": 0,
        "last_error": None,
        "result": "accepted",
        "message": "verification accepted",
    }
    assert manager.codes == ["246810"]
    assert manager.worker_creations == 0


@pytest.mark.parametrize("code", ["", "123", "12a4", "1234567890123", "１２３４"])
def test_email_code_rejects_malformed_values_without_echoing_submitted_value(code):
    app = build_login_api(ApiLoginManager())
    response = asyncio.run(
        login_request(
            app,
            "POST",
            "/api/tasks/api-task/email-code",
            headers={"X-API-Key": "api-test-key"},
            json={"code": code},
        )
    )

    assert response.status_code == 422
    if code:
        assert code not in response.text


def test_email_code_rejects_unknown_fields_without_echoing_secret_values():
    app = build_login_api(ApiLoginManager())
    secrets = {
        "code": "246810",
        "password": "password-never-returned",
        "proxy_url": "http://user:secret@proxy.example:8080",
        "cookies": "session-cookie-never-returned",
    }
    response = asyncio.run(
        login_request(
            app,
            "POST",
            "/api/tasks/api-task/email-code",
            headers={"X-API-Key": "api-test-key"},
            json=secrets,
        )
    )

    assert response.status_code == 422
    for secret in secrets.values():
        assert secret not in response.text
    for sensitive_name in ("password", "proxy_url", "cookies"):
        assert sensitive_name not in response.text


def test_login_endpoints_return_conflict_when_verification_is_not_waiting():
    app = build_login_api(ApiLoginManager(waiting=False))
    headers = {"X-API-Key": "api-test-key"}

    async def exercise():
        return await asyncio.gather(
            login_request(app, "GET", "/api/tasks/api-task/login-state", headers=headers),
            login_request(
                app,
                "POST",
                "/api/tasks/api-task/email-code",
                headers=headers,
                json={"code": "1234"},
            ),
            login_request(app, "POST", "/api/tasks/api-task/login-cancel", headers=headers),
        )

    responses = asyncio.run(exercise())
    assert [response.status_code for response in responses] == [409, 409, 409]
    assert all("1234" not in response.text for response in responses)


def test_login_endpoints_return_not_found_for_unknown_task():
    app = build_login_api(ApiLoginManager())
    headers = {"X-API-Key": "api-test-key"}

    async def exercise():
        return await asyncio.gather(
            login_request(app, "GET", "/api/tasks/missing/login-state", headers=headers),
            login_request(
                app,
                "POST",
                "/api/tasks/missing/email-code",
                headers=headers,
                json={"code": "1234"},
            ),
            login_request(app, "POST", "/api/tasks/missing/login-cancel", headers=headers),
        )

    responses = asyncio.run(exercise())
    assert [response.status_code for response in responses] == [404, 404, 404]


def test_cancel_login_returns_safe_public_result():
    app = build_login_api(ApiLoginManager())
    response = asyncio.run(
        login_request(
            app,
            "POST",
            "/api/tasks/api-task/login-cancel",
            headers={"X-API-Key": "api-test-key"},
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "task_id": "api-task",
        "status": "failed",
        "waiting": False,
        "attempts": 0,
        "remaining_seconds": 0,
        "last_error": "verification cancelled",
        "result": "cancelled",
        "message": "verification cancelled",
    }
    assert all(secret not in response.text for secret in ("code", "password", "cookie"))


def test_login_routes_are_registered():
    app = build_login_api(ApiLoginManager())
    registered = {(route.path, method) for route in app.routes for method in route.methods or ()}

    assert ("/api/tasks/{task_id}/login-state", "GET") in registered
    assert ("/api/tasks/{task_id}/email-code", "POST") in registered
    assert ("/api/tasks/{task_id}/login-cancel", "POST") in registered
