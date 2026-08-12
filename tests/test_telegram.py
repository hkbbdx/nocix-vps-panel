import asyncio
import threading
from dataclasses import dataclass, field

import httpx
import pytest
from cryptography.fernet import Fernet

from backend.app.config import Settings
from backend.app.db import create_engine, create_session_factory, init_db
from backend.app.main import create_app
from backend.app.repositories import Repository
from backend.app.schemas import TaskCreate
from backend.app.telegram import TelegramNotifier
from backend.app.worker import CheckoutWorker


TOKEN = "12345:" + "a" * 20
CHAT_ID = "-1001234567890"


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
    repo = Repository(create_session_factory(engine), settings)
    yield repo, settings, key
    engine.dispose()


def configure(repository, key):
    cipher = Fernet(key.encode("ascii"))
    repository.set_settings(
        {
            "telegram_bot_token": cipher.encrypt(TOKEN.encode()).decode("ascii"),
            "telegram_chat_id": cipher.encrypt(CHAT_ID.encode()).decode("ascii"),
            "telegram_enabled": "true",
        }
    )


def notifier_for(repository, settings, transport, logger=None):
    def client_factory(**kwargs):
        return httpx.AsyncClient(transport=transport, **kwargs)

    return TelegramNotifier(
        repository,
        settings,
        client_factory=client_factory,
        logger=logger,
    )


def run(coro):
    return asyncio.run(coro)


def test_unconfigured_notifier_is_safe_and_does_not_call_telegram(repository):
    repo, settings, _ = repository
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request))
    notifier = notifier_for(repo, settings, transport)

    assert notifier.is_configured() is False
    assert run(notifier.send("hello")) is False
    assert run(notifier.test()) is False
    assert calls == []


def test_repository_reads_telegram_settings_as_one_snapshot(repository):
    repo, _, key = repository
    configure(repo, key)

    snapshot = repo.get_telegram_settings()

    assert snapshot["telegram_enabled"] == "true"
    assert snapshot["telegram_bot_token"] is not None
    assert snapshot["telegram_chat_id"] is not None


def test_notifier_uses_one_settings_snapshot_for_configuration_and_send(repository):
    repo, settings, key = repository
    configure(repo, key)
    snapshots = []
    original = repo.get_telegram_settings

    def snapshot():
        value = original()
        snapshots.append(value)
        return value

    repo.get_telegram_settings = snapshot
    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True})
        ),
    )

    assert notifier.is_configured() is True
    assert run(notifier.send("hello")) is True
    assert len(snapshots) == 2


def test_notifier_sends_redacted_task_and_product_message_with_ten_second_timeout(
    repository,
):
    repo, settings, key = repository
    configure(repo, key)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    notifier = notifier_for(repo, settings, httpx.MockTransport(handler))

    assert run(
        notifier.send(
            {
                "task_id": "task-1",
                "product_id": "418",
                "message": (
                    "password=secret token=paypal-token cookie=session-cookie "
                    "card_number=4111111111111111"
                ),
            }
        )
    ) is True

    assert len(requests) == 1
    assert requests[0].url.path.endswith(f"/bot{TOKEN}/sendMessage")
    assert requests[0].url.path.count(TOKEN) == 1
    body = httpx.QueryParams(requests[0].content.decode())
    text = body["text"]
    assert "task-1" in text
    assert "418" in text
    for secret in ("secret", "paypal-token", "session-cookie", "4111111111111111"):
        assert secret not in text
    assert "password=***REDACTED***" in text
    assert "token=***REDACTED***" in text
    assert "cookie=***REDACTED***" in text
    assert "card_number=***REDACTED***" in text


def test_notifier_reports_success_for_valid_telegram_response(repository):
    repo, settings, key = repository
    configure(repo, key)
    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "result": {}})
        ),
    )

    assert run(notifier.test()) is True


def test_test_notification_uses_configured_credentials_when_notifications_disabled(
    repository,
):
    repo, settings, key = repository
    configure(repo, key)
    repo.set_setting("telegram_enabled", "false")
    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "result": {}})
        ),
    )

    assert run(notifier.test()) is True


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"ok": False, "description": "bad request"}),
        httpx.Response(200, json={"ok": False, "description": "bot blocked"}),
        httpx.Response(200, content=b"not-json"),
    ],
)
def test_notifier_treats_http_api_and_malformed_responses_as_nonfatal(
    repository, response
):
    repo, settings, key = repository
    configure(repo, key)
    logs = []
    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(lambda request: response),
        logger=logs.append,
    )

    assert run(notifier.send("password=secret")) is False
    assert logs
    assert all("secret" not in message for message in logs)


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("timed out"), httpx.ConnectError("offline")],
)
def test_notifier_treats_network_errors_as_nonfatal(repository, error):
    repo, settings, key = repository
    configure(repo, key)
    logs = []

    def handler(request):
        raise error

    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(handler),
        logger=logs.append,
    )

    assert run(notifier.send("token=secret")) is False
    assert logs
    assert all("secret" not in message for message in logs)


def test_notifier_does_not_log_bot_token_from_network_exception(repository):
    repo, settings, key = repository
    configure(repo, key)
    logs = []

    def handler(request):
        raise httpx.ConnectError(f"failed to connect to {request.url}")

    notifier = notifier_for(
        repo,
        settings,
        httpx.MockTransport(handler),
        logger=logs.append,
    )

    assert run(notifier.send("hello")) is False
    assert logs
    assert TOKEN not in " ".join(logs)


def test_notifier_warning_is_persisted_and_safe_when_http_fails(repository):
    repo, settings, key = repository
    configure(repo, key)

    def handler(request):
        raise httpx.ConnectError(f"failed {request.url} cookie=session-cookie")

    notifier = notifier_for(repo, settings, httpx.MockTransport(handler))

    assert run(notifier.send({"task_id": "task-1", "product_id": "418", "message": "hello"})) is False

    logs = repo.list_logs(None, "WARNING", 10)
    assert logs
    assert all("session-cookie" not in log.message for log in logs)
    assert all(TOKEN not in log.message and CHAT_ID not in log.message for log in logs)


def test_notifier_returns_false_when_persistent_logging_fails():
    class Repository:
        def get_telegram_settings(self):
            return {
                "telegram_enabled": "true",
                "telegram_bot_token": "invalid-ciphertext",
                "telegram_chat_id": "invalid-ciphertext",
            }

        def append_log(self, *args):
            raise RuntimeError("logging database unavailable")

    logs = []
    notifier = TelegramNotifier(
        Repository(),
        Settings(data_encryption_key=Fernet.generate_key().decode("ascii")),
        logger=logs.append,
    )

    assert run(notifier.send("hello")) is False
    assert logs


@pytest.mark.parametrize("method", ["send", "test"])
def test_notifier_configuration_lookup_failures_are_nonfatal_and_redacted(method):
    class FailingRepository:
        def get_setting(self, key):
            raise RuntimeError(
                "token=secret-token ciphertext=secret-ciphertext chat_id=-1001234567890"
            )

    settings = Settings(data_encryption_key=Fernet.generate_key().decode("ascii"))
    logs = []
    notifier = TelegramNotifier(FailingRepository(), settings, logger=logs.append)

    result = (
        notifier.test()
        if method == "test"
        else notifier.send("task-1")
    )
    assert run(result) is False
    assert logs
    joined = " ".join(logs)
    assert "secret-token" not in joined
    assert "secret-ciphertext" not in joined
    assert "-1001234567890" not in joined


def test_notifier_uses_a_ten_second_http_timeout(repository):
    repo, settings, key = repository
    configure(repo, key)
    timeouts = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return httpx.Response(200, json={"ok": True})

    def client_factory(**kwargs):
        timeouts.append(kwargs["timeout"])
        return FakeClient()

    notifier = TelegramNotifier(repo, settings, client_factory=client_factory)
    assert run(notifier.send("hello")) is True
    assert timeouts == [10.0]


def test_worker_thread_uses_real_notifier_send_sync_with_mocked_transport(repository):
    repo, settings, key = repository
    configure(repo, key)
    task = repo.create_task(
        TaskCreate(
            goods_id="418",
            target_price=59,
            wait_interval=2,
            email="buyer@example.com",
            password="worker-password",
        )
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    notifier = notifier_for(repo, settings, httpx.MockTransport(handler))
    worker = CheckoutWorker(
        task,
        client_factory=SuccessfulClient,
        repository=repo,
        notifier=notifier,
    )
    thread = threading.Thread(target=worker.run)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert repo.list_orders(task.id)[0].status == "success"
    assert len(requests) == 1
    body = httpx.QueryParams(requests[0].content.decode())
    assert task.id in body["text"]
    assert "418" in body["text"]


def test_settings_round_trip_stores_telegram_credentials_as_ciphertext(repository):
    repo, settings, key = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings",
                    headers={"X-API-Key": "test-api-key"},
                    json={
                        "telegram_bot_token": TOKEN,
                        "telegram_chat_id": CHAT_ID,
                        "telegram_enabled": True,
                    },
                )
                fetched = await client.get(
                    "/api/settings", headers={"X-API-Key": "test-api-key"}
                )
        return response, fetched

    response, fetched = run(exercise())
    token_ciphertext = app.state.repository.get_setting("telegram_bot_token")
    chat_ciphertext = app.state.repository.get_setting("telegram_chat_id")
    assert response.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["telegram_configured"] is True
    assert TOKEN not in fetched.text
    assert CHAT_ID not in fetched.text
    assert token_ciphertext not in (None, TOKEN)
    assert chat_ciphertext not in (None, CHAT_ID)
    cipher = Fernet(key.encode("ascii"))
    assert cipher.decrypt(token_ciphertext.encode()).decode() == TOKEN
    assert cipher.decrypt(chat_ciphertext.encode()).decode() == CHAT_ID


def test_settings_reject_unknown_and_card_fields_and_test_endpoint_requires_auth(
    repository,
):
    _, settings, _ = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                unauthorized = await client.post("/api/telegram/test")
                invalid = await client.put(
                    "/api/settings",
                    headers={"X-API-Key": "test-api-key"},
                    json={"cc_num": "4111111111111111"},
                )
        return unauthorized, invalid

    unauthorized, invalid = run(exercise())
    assert unauthorized.status_code == 401
    assert invalid.status_code == 422


def test_telegram_test_endpoint_returns_safe_failure(repository):
    _, settings, _ = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            app.state.telegram_notifier = type(
                "FailingNotifier",
                (),
                {"test": lambda self: _failed_test()},
            )()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post(
                    "/api/telegram/test", headers={"X-API-Key": "test-api-key"}
                )

    async def _failed_test():
        return False

    response = run(exercise())
    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "Telegram test notification failed",
    }


@dataclass
class WorkerTask:
    id: str = "task-1"
    goods_id: str = "418"
    target_price: float = 59
    wait_interval: float = 2
    operating_system: str = "debian"
    email: str = "buyer@example.com"


@dataclass
class WorkerRepository:
    statuses: list = field(default_factory=list)
    orders: list = field(default_factory=list)

    def get_decrypted_password(self, task_id):
        return "password"

    def set_task_status(self, task_id, status, error=None):
        self.statuses.append((task_id, status, error))

    def create_order(self, task_id, status, observed_price=None, error=None):
        self.orders.append((task_id, status, observed_price, error))


class SuccessfulClient:
    current_url = "https://nocix.net/cart/?id=418"

    def check_stock(self, goods_id):
        return True

    def open_cart(self, goods_id):
        pass

    def select_operating_system(self, value):
        return True

    def match_price(self, value):
        return True

    def fill_in_customer_info(self, **kwargs):
        pass

    def fill_in_payment_info(self, **kwargs):
        pass

    def click_next_step_button(self):
        pass

    def submit_order(self):
        return None

    def close(self):
        pass


def test_worker_continues_and_creates_one_order_when_notifier_fails():
    repository = WorkerRepository()

    def fail_notification(message):
        raise RuntimeError("bot_token=secret")

    worker = CheckoutWorker(
        WorkerTask(),
        client_factory=SuccessfulClient,
        repository=repository,
        notifier=fail_notification,
    )

    worker.run()

    assert repository.statuses[-1][1] == "success"
    assert repository.orders == [("task-1", "success", None, None)]


def test_worker_passes_task_and_product_context_to_notifier_interface():
    repository = WorkerRepository()
    events = []

    class InterfaceNotifier:
        def send_sync(self, event):
            events.append(event)
            return True

    worker = CheckoutWorker(
        WorkerTask(),
        client_factory=SuccessfulClient,
        repository=repository,
        notifier=InterfaceNotifier(),
    )

    worker.run()

    assert events[-1]["task_id"] == "task-1"
    assert events[-1]["product_id"] == "418"
