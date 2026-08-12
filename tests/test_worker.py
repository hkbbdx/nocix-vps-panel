import threading
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from backend.app.worker import CheckoutWorker
from nocix_fucker.types import PaymentMethod


@dataclass
class FakeTask:
    id: str = "task-1"
    goods_id: str = "418"
    target_price: float = 59.0
    wait_interval: float = 5.0
    operating_system: str = "debian"
    email: str = "buyer@example.com"
    password: str = "secret-password"
    new_customer: bool = False
    payment_method: str = "paypal"
    auto_submit: bool = True


@dataclass
class FakeClient:
    stock: list[bool]
    prices_match: bool = True
    os_results: dict[str, bool] = field(
        default_factory=lambda: {"debian": True, "ubuntu": True}
    )
    submit_result: str | None = None
    current_url: str = "https://nocix.net/cart/?id=418"
    close_error: Exception | None = None
    last_price_text: str | None = None
    calls: list[tuple] = field(default_factory=list)
    closed: bool = False

    def check_stock(self, goods_id, stock_url=None):
        self.calls.append(("check_stock", goods_id) if stock_url is None else ("check_stock", goods_id, stock_url))
        return self.stock.pop(0) if self.stock else False

    def open_cart(self, goods_id, cart_url=None):
        self.calls.append(("open_cart", goods_id) if cart_url is None else ("open_cart", goods_id, cart_url))

    def select_operating_system(self, value):
        self.calls.append(("select_operating_system", value))
        return self.os_results.get(value, False)

    def match_price(self, target_price):
        self.calls.append(("match_price", target_price))
        return self.prices_match

    def fill_in_customer_info(self, **kwargs):
        self.calls.append(("fill_in_customer_info", kwargs))

    def fill_in_payment_info(self, **kwargs):
        self.calls.append(("fill_in_payment_info", kwargs))

    def click_next_step_button(self):
        self.calls.append(("click_next_step_button",))

    def submit_order(self):
        self.calls.append(("submit_order",))
        return self.submit_result

    def close(self):
        self.closed = True
        self.calls.append(("close",))
        if self.close_error is not None:
            raise self.close_error


@dataclass
class FakeRepository:
    statuses: list[tuple] = field(default_factory=list)
    orders: list[tuple] = field(default_factory=list)

    def get_decrypted_password(self, task_id):
        return "secret-password"

    def set_task_status(self, task_id, status, error=None):
        self.statuses.append((task_id, status, error))

    def create_order(self, task_id, status, observed_price=None, error=None):
        self.orders.append((task_id, status, observed_price, error))


@dataclass
class SubmissionRaceRepository:
    status: str = "ordering"
    orders: list[tuple] = field(default_factory=list)
    finalize_calls: int = 0

    def get_decrypted_password(self, task_id):
        return "secret-password"

    def set_task_status(self, task_id, status, error=None):
        self.status = status

    def create_order(self, task_id, status, observed_price=None, error=None):
        self.orders.append((task_id, status, observed_price, error))

    def finalize_submission(
        self, task_id, task_status, order_status, observed_price=None, error=None
    ):
        self.finalize_calls += 1
        # Model stop winning after submit_order() but before terminal persistence.
        self.status = "stopped"
        if self.status == "stopped":
            self.status = "submitted_pending_confirmation"
            self.create_order(task_id, "unknown", observed_price, "interrupted after submit: stopped")
            return SimpleNamespace(status=self.status)
        self.status = task_status
        self.create_order(task_id, order_status, observed_price, error)
        return SimpleNamespace(status=self.status)


@dataclass
class SubmissionErrorRaceRepository(SubmissionRaceRepository):
    def finalize_submission(
        self, task_id, task_status, order_status, observed_price=None, error=None
    ):
        self.finalize_calls += 1
        self.status = "stopped"
        self.status = "submitted_pending_confirmation"
        self.create_order(
            task_id,
            "unknown",
            observed_price,
            error or "submission outcome is unknown",
        )
        return SimpleNamespace(status=self.status)


@dataclass
class UnavailableSubmissionRepository(FakeRepository):
    status: str = "ordering"

    def set_task_status(self, task_id, status, error=None):
        if status in {"success", "failed", "unknown", "submitted_pending_confirmation"}:
            raise RuntimeError("database unavailable")
        self.status = status
        super().set_task_status(task_id, status, error)

    def create_order(self, task_id, status, observed_price=None, error=None):
        raise RuntimeError("database unavailable")


@dataclass
class EmptySubmissionRepository(FakeRepository):
    def finalize_submission(
        self, task_id, task_status, order_status, observed_price=None, error=None
    ):
        return None

    def finalize_submission(
        self, task_id, task_status, order_status, observed_price=None, error=None
    ):
        raise RuntimeError("database unavailable")


def build_worker(client, task=None, **kwargs):
    repository = kwargs.pop("repository", FakeRepository())
    return CheckoutWorker(
        task or FakeTask(),
        client_factory=kwargs.pop("client_factory", lambda: client),
        repository=repository,
        **kwargs,
    ), repository


def test_worker_waits_when_out_of_stock():
    client = FakeClient([False, False, True])
    sleeps = []
    now = [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    worker, repository = build_worker(
        client, sleep=sleep, clock=lambda: now[0]
    )

    worker.run()

    assert [call[0] for call in client.calls] == [
        "check_stock",
        "check_stock",
        "check_stock",
        "open_cart",
        "select_operating_system",
        "match_price",
        "fill_in_customer_info",
        "fill_in_payment_info",
        "click_next_step_button",
        "submit_order",
        "close",
    ]
    assert sleeps == [1.0] * 10
    assert repository.statuses[0][1] == "checking"


def test_worker_notifies_on_stock_recovery_before_checkout_without_secrets():
    client = FakeClient([False, True])
    notifications = []
    worker, _ = build_worker(client, notifier=notifications.append)

    worker.run()

    assert notifications
    recovery = notifications[0]
    assert "task-1" in recovery
    assert "418" in recovery
    assert "secret-password" not in recovery
    assert "paypal-token" not in recovery
    assert [call[0] for call in client.calls].index("open_cart") > 0


def test_worker_pauses_if_pause_event_is_set_during_active_polling():
    client = FakeClient([False, True])
    pause_event = threading.Event()

    def check_stock(goods_id):
        client.calls.append(("check_stock", goods_id))
        pause_event.set()
        return False

    client.check_stock = check_stock
    worker, repository = build_worker(client, pause_event=pause_event)

    worker.run()

    assert [status[1] for status in repository.statuses] == ["checking", "paused"]
    assert [call[0] for call in client.calls] == ["check_stock", "close"]


def test_worker_stops_if_stop_event_is_set_during_active_polling_and_stays_terminal():
    client = FakeClient([True])
    stop_event = threading.Event()

    def check_stock(goods_id):
        client.calls.append(("check_stock", goods_id))
        stop_event.set()
        return True

    client.check_stock = check_stock
    worker, repository = build_worker(client, stop_event=stop_event)

    worker.run()
    worker.run()

    assert [status[1] for status in repository.statuses] == ["checking", "stopped"]
    assert [call[0] for call in client.calls] == ["check_stock", "close"]


def test_worker_persists_pause_when_injected_wait_sets_pause_event():
    client = FakeClient([False, True])
    pause_event = threading.Event()
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        pause_event.set()

    worker, repository = build_worker(
        client,
        pause_event=pause_event,
        sleep=sleep,
        clock=lambda: now[0],
    )

    worker.run()

    assert [status[1] for status in repository.statuses] == ["checking", "paused"]
    assert [call[0] for call in client.calls] == ["check_stock", "close"]


def test_worker_persists_terminal_stop_when_injected_wait_sets_stop_event():
    client = FakeClient([False, True])
    stop_event = threading.Event()
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        stop_event.set()

    worker, repository = build_worker(
        client,
        stop_event=stop_event,
        sleep=sleep,
        clock=lambda: now[0],
    )

    worker.run()
    worker.run()

    assert [status[1] for status in repository.statuses] == ["checking", "stopped"]
    assert [call[0] for call in client.calls] == ["check_stock", "close"]


def test_worker_starts_checkout_when_stock_returns():
    client = FakeClient([True])
    worker, _ = build_worker(client)

    worker.run()

    assert ("open_cart", "418") in client.calls
    assert ("select_operating_system", "debian") in client.calls


def test_worker_falls_back_from_debian_to_ubuntu_only_when_needed():
    client = FakeClient([True], os_results={"debian": False, "ubuntu": True})
    worker, _ = build_worker(client)

    worker.run()

    assert client.calls.count(("select_operating_system", "debian")) == 1
    assert client.calls.count(("select_operating_system", "ubuntu")) == 1


def test_worker_stops_on_price_mismatch_without_filling_credentials():
    client = FakeClient([True], prices_match=False)
    worker, repository = build_worker(client)

    worker.run()

    assert not any(call[0] == "fill_in_customer_info" for call in client.calls)
    assert not any(call[0] == "fill_in_payment_info" for call in client.calls)
    assert len([call for call in client.calls if call[0] == "submit_order"]) == 0
    assert repository.orders[-1][1] == "failed"


def test_worker_uses_existing_customer_paypal_flow_without_card_fields():
    client = FakeClient([True])
    worker, _ = build_worker(client)

    worker.run()

    customer = next(call[1] for call in client.calls if call[0] == "fill_in_customer_info")
    payment = next(call[1] for call in client.calls if call[0] == "fill_in_payment_info")
    assert customer["new"] is False
    assert customer["email"] == "buyer@example.com"
    assert customer["password"] == "secret-password"
    assert payment == {"payment_method": PaymentMethod.PAYPAL}


def test_worker_records_submit_error_and_does_not_retry():
    client = FakeClient([True], submit_result="order rejected")
    worker, repository = build_worker(client)

    worker.run()
    worker.run()

    assert len([call for call in client.calls if call[0] == "submit_order"]) == 1
    assert repository.orders[-1][1:] == ("failed", None, "order rejected")


def test_worker_pause_performs_no_browser_work_and_stop_exits_promptly():
    client = FakeClient([True])
    pause_event = threading.Event()
    pause_event.set()
    stop_event = threading.Event()
    sleeps = []

    created = []
    worker, repository = build_worker(
        client,
        pause_event=pause_event,
        stop_event=stop_event,
        sleep=lambda seconds: sleeps.append(seconds),
        client_factory=lambda: created.append(client) or client,
    )
    worker.run()
    assert created == []
    assert client.calls == []

    stop_event.set()
    worker.run()
    assert client.calls == []
    assert not sleeps
    assert [status[1] for status in repository.statuses] == ["paused", "stopped"]


def test_client_paypal_path_selects_paypal_and_accepts_terms_without_card_fields():
    from nocix_fucker.client import Client

    client = Client.__new__(Client)
    calls = []
    client._select_payment_method = lambda value: calls.append(("select", value))
    client._accept_terms = lambda: calls.append(("terms",))
    client._fill_in_credit_card_info = lambda **kwargs: calls.append(("card", kwargs))

    client.fill_in_payment_info(payment_method=PaymentMethod.PAYPAL)

    assert calls == [("select", "paypal"), ("terms",)]


def test_worker_prevents_duplicate_submit_on_repeated_run():
    client = FakeClient([True])
    worker, _ = build_worker(client)

    worker.run()
    worker.run()

    assert [call[0] for call in client.calls].count("submit_order") == 1


def test_worker_blocks_paypal_redirect_and_records_url():
    client = FakeClient([True], current_url="https://www.paypal.com/checkoutnow")
    worker, repository = build_worker(client)

    worker.run()

    assert not any(call[0] == "fill_in_customer_info" for call in client.calls)
    assert not any(call[0] == "submit_order" for call in client.calls)
    assert repository.orders[-1][1] == "failed"
    assert "paypal.com" in repository.orders[-1][3]


def test_worker_blocks_paypal_redirect_after_payment_before_continue():
    client = FakeClient([True])

    def fill_payment(**kwargs):
        client.calls.append(("fill_in_payment_info", kwargs))
        client.current_url = "https://www.paypal.com/signin/authorize?token=secret-token"

    client.fill_in_payment_info = fill_payment
    worker, repository = build_worker(client)

    worker.run()

    assert [call[0] for call in client.calls].count("submit_order") == 0
    assert repository.orders[-1][1] == "failed"
    assert "paypal.com" in repository.orders[-1][3]


def test_worker_blocks_paypal_redirect_after_every_continue_before_submit():
    client = FakeClient([True])

    def click_next():
        client.calls.append(("click_next_step_button",))
        client.current_url = "https://paypal.com/checkoutnow?token=secret-token"

    client.click_next_step_button = click_next
    worker, repository = build_worker(client)

    worker.run()

    assert [call[0] for call in client.calls].count("submit_order") == 0
    assert repository.orders[-1][1] == "failed"
    assert "paypal.com" in repository.orders[-1][3]


def test_worker_does_not_misclassify_normal_nocix_url_containing_paypal():
    client = FakeClient([True], current_url="https://nocix.net/paypal/authorize")
    worker, repository = build_worker(client)

    worker.run()

    assert repository.statuses[-1][1] == "success"
    assert [call[0] for call in client.calls].count("submit_order") == 1


def test_worker_persists_success_order_notifies_and_closes_client():
    client = FakeClient([True])
    notifications = []
    worker, repository = build_worker(client, notifier=notifications.append)

    worker.run()

    assert repository.statuses[-1][1] == "success"
    assert repository.orders[-1] == ("task-1", "success", None, None)
    assert notifications == ["Task task-1 order submitted"]
    assert client.closed is True


@pytest.mark.parametrize(
    "client, expected_fragment",
    [
        (FakeClient([False, True]), "stock recovered"),
        (FakeClient([True]), "order submitted"),
        (FakeClient([True], prices_match=False), "price mismatch"),
    ],
)
def test_worker_terminal_notifications_are_not_duplicated_on_repeated_runs(
    client, expected_fragment
):
    notifications = []
    worker, _ = build_worker(client, notifier=notifications.append)

    worker.run()
    worker.run()

    assert len([message for message in notifications if expected_fragment in message]) == 1


def test_worker_concurrent_runs_emit_one_success_notification():
    client = FakeClient([True])
    notifications = []
    started = threading.Event()
    release = threading.Event()

    def client_factory():
        started.set()
        release.wait(timeout=2)
        return client

    worker, _ = build_worker(
        client,
        client_factory=client_factory,
        notifier=notifications.append,
    )
    first = threading.Thread(target=worker.run)
    first.start()
    assert started.wait(timeout=2)
    second = threading.Thread(target=worker.run)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert notifications.count("Task task-1 order submitted") == 1


def test_worker_concurrent_runs_emit_one_failure_notification():
    client = FakeClient([True], prices_match=False)
    notifications = []
    started = threading.Event()
    release = threading.Event()

    def client_factory():
        started.set()
        release.wait(timeout=2)
        return client

    worker, _ = build_worker(
        client,
        client_factory=client_factory,
        notifier=notifications.append,
    )
    first = threading.Thread(target=worker.run)
    first.start()
    assert started.wait(timeout=2)
    second = threading.Thread(target=worker.run)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len([message for message in notifications if "price mismatch" in message]) == 1


@pytest.mark.parametrize("failure", ["os", "price", "payment", "submit"])
def test_worker_closes_client_on_all_terminal_paths(failure):
    client = FakeClient([True], prices_match=failure != "price")
    if failure == "os":
        client.os_results = {"debian": False, "ubuntu": False}
    if failure == "payment":
        def fail_payment(**kwargs):
            raise RuntimeError("payment failed")

        client.fill_in_payment_info = fail_payment
    if failure == "submit":
        client.submit_result = "submit failed"
    worker, _ = build_worker(client)

    worker.run()

    assert client.closed is True


def test_worker_logs_never_contain_password_or_payment_secrets():
    client = FakeClient([True], submit_result="password=secret-password token=paypal-token")
    logs = []
    worker, _ = build_worker(client, logger=logs.append)

    worker.run()

    joined = " ".join(logs)
    assert "secret-password" not in joined
    assert "paypal-token" not in joined
    assert "password=***REDACTED***" in joined


def test_worker_notifier_redacts_password_tokens_and_cookies():
    client = FakeClient(
        [True],
        submit_result="password=secret-password token=paypal-token cookie=session-cookie",
    )
    notifications = []
    worker, _ = build_worker(client, notifier=notifications.append)

    worker.run()

    message = " ".join(notifications)
    assert "secret-password" not in message
    assert "paypal-token" not in message
    assert "session-cookie" not in message
    assert "password=***REDACTED***" in message
    assert "token=***REDACTED***" in message
    assert "cookie=***REDACTED***" in message


def test_concurrent_run_calls_have_one_owner_and_one_submit():
    client = FakeClient([True])
    factory_started = threading.Event()
    release_factory = threading.Event()
    factory_calls = []

    def client_factory():
        factory_calls.append(1)
        factory_started.set()
        release_factory.wait(timeout=2)
        return client

    worker, _ = build_worker(client, client_factory=client_factory)
    first = threading.Thread(target=worker.run)
    first.start()
    assert factory_started.wait(timeout=2)

    worker.run()

    release_factory.set()
    first.join(timeout=2)
    assert not first.is_alive()
    assert len(factory_calls) == 1
    assert [call[0] for call in client.calls].count("submit_order") == 1


def test_pause_during_checkout_persists_paused_and_closes_without_submit():
    client = FakeClient([True])
    pause_event = threading.Event()

    def select_os(value):
        client.calls.append(("select_operating_system", value))
        pause_event.set()
        return True

    client.select_operating_system = select_os
    worker, repository = build_worker(client, pause_event=pause_event)

    worker.run()

    assert repository.statuses[-1][1] == "paused"
    assert not any(call[0] == "submit_order" for call in client.calls)
    assert client.closed is True


def test_stop_during_checkout_persists_stopped_and_cannot_retry():
    client = FakeClient([True])
    stop_event = threading.Event()

    def fill_payment(**kwargs):
        client.calls.append(("fill_in_payment_info", kwargs))
        stop_event.set()

    client.fill_in_payment_info = fill_payment
    worker, repository = build_worker(client, stop_event=stop_event)

    worker.run()
    worker.run()

    assert repository.statuses[-1][1] == "stopped"
    assert [call[0] for call in client.calls].count("submit_order") == 0
    assert client.closed is True


def test_post_submit_paypal_redirect_is_blocked_and_sanitized():
    client = FakeClient([True])

    def submit_order():
        client.calls.append(("submit_order",))
        client.current_url = (
            "https://www.paypal.com/signin/authorize?token=secret-token"
            "&code=secret-code#fragment"
        )
        return None

    client.submit_order = submit_order
    logs = []
    notifications = []
    worker, repository = build_worker(
        client, logger=logs.append, notifier=notifications.append
    )

    worker.run()

    messages = str(repository.orders[-1]) + " " + " ".join(logs + notifications)
    assert repository.statuses[-1][1] == "submitted_pending_confirmation"
    assert repository.orders[-1][1] == "unknown"
    assert "paypal.com/signin/authorize" in messages
    assert "secret-token" not in messages
    assert "secret-code" not in messages
    assert "fragment" not in messages


def test_successful_worker_survives_cleanup_exception_without_retry():
    client = FakeClient([True], close_error=RuntimeError("close failed"))
    worker, repository = build_worker(client)

    worker.run()
    worker.run()

    assert repository.statuses[-1][1] == "success"
    assert len(repository.orders) == 1
    assert [call[0] for call in client.calls].count("submit_order") == 1


def test_post_submit_persistence_failure_is_terminal_and_blocks_retries():
    client = FakeClient([True])
    repository = UnavailableSubmissionRepository()
    logs = []
    notifications = []
    worker, _ = build_worker(
        client,
        repository=repository,
        logger=logs.append,
        notifier=notifications.append,
    )

    worker.run()
    worker.run()

    assert worker._persistence_blocked is True
    assert repository.status == "ordering"
    assert not any(status[1] in {"success", "failed", "stopped"} for status in repository.statuses)
    assert len([call for call in client.calls if call[0] == "submit_order"]) == 1
    assert any("persistence" in message.lower() for message in logs + notifications)


def test_empty_submission_finalization_falls_back_to_indeterminate_without_success():
    client = FakeClient([True])
    repository = EmptySubmissionRepository()
    worker, _ = build_worker(client, repository=repository)

    worker.run()

    assert worker._persistence_blocked is False
    assert repository.statuses[-1][1] == "submitted_pending_confirmation"
    assert repository.orders[-1][1] == "unknown"
    assert len([call for call in client.calls if call[0] == "submit_order"]) == 1


def test_callback_exceptions_do_not_change_success_or_duplicate_order():
    client = FakeClient([True])

    def raising_callback(message):
        raise RuntimeError("callback password=secret-password")

    worker, repository = build_worker(
        client, logger=raising_callback, notifier=raising_callback
    )

    worker.run()
    worker.run()

    assert repository.statuses[-1][1] == "success"
    assert len(repository.orders) == 1
    assert [call[0] for call in client.calls].count("submit_order") == 1


def test_pause_during_password_retrieval_prevents_customer_entry():
    client = FakeClient([True])
    pause_event = threading.Event()

    class Repository(FakeRepository):
        def get_decrypted_password(self, task_id):
            pause_event.set()
            return "secret-password"

    repository = Repository()
    worker, _ = build_worker(client, repository=repository, pause_event=pause_event)

    worker.run()

    assert repository.statuses[-1][1] == "paused"
    assert not any(call[0] == "fill_in_customer_info" for call in client.calls)
    assert not repository.orders
    assert client.closed is True


@pytest.mark.parametrize("event_name", ["stop_event", "pause_event"])
def test_interruption_during_submit_cannot_record_success(event_name):
    client = FakeClient([True])
    event = threading.Event()

    def submit_order():
        client.calls.append(("submit_order",))
        event.set()
        return None

    client.submit_order = submit_order
    worker, repository = build_worker(client, **{event_name: event})

    worker.run()

    expected_status = "stopped" if event_name == "stop_event" else "paused"
    assert repository.statuses[-1][1] == "submitted_pending_confirmation"
    assert [call[0] for call in client.calls].count("submit_order") == 1
    assert not any(order[1] == "success" for order in repository.orders)
    assert repository.orders[-1][1] == "unknown"
    assert repository.orders[-1][3] == f"interrupted after submit: {expected_status}"
    assert client.closed is True


def test_submission_finalization_is_atomic_when_stop_wins_after_submit():
    client = FakeClient([True])
    repository = SubmissionRaceRepository()
    worker, _ = build_worker(client, repository=repository)

    worker.run()

    assert repository.finalize_calls == 1
    assert repository.status == "submitted_pending_confirmation"
    assert repository.orders == [
        ("task-1", "unknown", None, "interrupted after submit: stopped")
    ]


def test_submit_error_finalization_is_atomic_when_stop_wins_after_submit():
    client = FakeClient([True], submit_result="order rejected")
    repository = SubmissionErrorRaceRepository()
    worker, _ = build_worker(client, repository=repository)

    worker.run()

    assert repository.finalize_calls == 1
    assert repository.status == "submitted_pending_confirmation"
    assert repository.orders[-1][1:] == (
        "unknown",
        None,
        "order rejected",
    )


def test_exception_after_submit_is_indeterminate_and_not_retryable():
    client = FakeClient([True])

    def submit_order():
        client.calls.append(("submit_order",))
        raise RuntimeError("browser disconnected")

    client.submit_order = submit_order
    worker, repository = build_worker(client)

    worker.run()
    worker.run()

    assert repository.statuses[-1][1] == "submitted_pending_confirmation"
    assert repository.orders[-1][1] == "unknown"
    assert len([call for call in client.calls if call[0] == "submit_order"]) == 1


def test_observed_price_is_recorded_for_success_failure_and_indeterminate():
    success_client = FakeClient([True], last_price_text="$59.00")
    success_worker, success_repository = build_worker(success_client)
    success_worker.run()

    failure_client = FakeClient([True], prices_match=False, last_price_text="$72.00")
    failure_worker, failure_repository = build_worker(failure_client)
    failure_worker.run()

    unknown_client = FakeClient([True], last_price_text="$59.00")
    unknown_client.submit_order = lambda: (_ for _ in ()).throw(RuntimeError("lost"))
    unknown_worker, unknown_repository = build_worker(unknown_client)
    unknown_worker.run()

    assert success_repository.orders[-1][2] == "$59.00"
    assert failure_repository.orders[-1][2] == "$72.00"
    assert unknown_repository.orders[-1][2] == "$59.00"


def test_worker_uses_configured_nocix_urls():
    task = FakeTask()
    task.stock_url = "https://shop.nocix.net/custom-stock?id=418"
    task.cart_url = "https://checkout.nocix.net/custom-cart?id=418"
    client = FakeClient([True])
    worker, _ = build_worker(client, task=task)

    worker.run()

    assert ("check_stock", "418", task.stock_url) in client.calls
    assert ("open_cart", "418", task.cart_url) in client.calls


def test_client_init_quits_driver_when_setup_raises(monkeypatch):
    from nocix_fucker.client import Client

    class Driver:
        def __init__(self):
            self.quit_calls = 0

        def maximize_window(self):
            raise RuntimeError("maximize failed")

        def quit(self):
            self.quit_calls += 1

    driver = Driver()
    monkeypatch.setattr(
        "nocix_fucker.client.webdriver.Remote", lambda **kwargs: driver
    )

    with pytest.raises(RuntimeError, match="maximize failed"):
        Client("http://browser", None)

    assert driver.quit_calls == 1
