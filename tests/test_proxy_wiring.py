import asyncio
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet

from backend.app.config import Settings
from backend.app.db import create_engine, create_session_factory, init_db
from backend.app.main import create_app
from backend.app.manager import TaskManager
from backend.app.proxy import ProxyConfig
from backend.app.repositories import Repository
from backend.app.schemas import TaskCreate
from nocix_fucker.client import (
    Client,
    ProxyInitializationError,
    _create_http_auth_extension,
    proxy_capabilities,
)


def task_data(**overrides):
    data = {
        "goods_id": "418",
        "target_price": 59,
        "wait_interval": 5,
        "email": "buyer@example.com",
        "password": "task-password",
    }
    data.update(overrides)
    return TaskCreate(**data)


@pytest.fixture
def repository(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        api_key="test-api-key",
        data_dir=str(tmp_path),
        data_encryption_key=key,
    )
    engine = create_engine(settings, database_url=f"sqlite:///{tmp_path / 'nocix.db'}")
    init_db(engine)
    try:
        yield Repository(create_session_factory(engine), settings), settings
    finally:
        engine.dispose()


def test_effective_proxy_returns_structured_config_with_task_precedence(repository):
    repo, _ = repository
    inherited = repo.create_task(task_data())
    custom = repo.create_task(
        task_data(proxy_mode="custom", proxy_url="socks5://custom-user:custom-pass@custom.example:1080")
    )
    direct = repo.create_task(task_data(proxy_mode="direct"))
    repo.update_proxy_settings(
        proxy_enabled=True,
        proxy_url="http://global-user:global-pass@global.example:3128",
    )

    assert repo.get_effective_proxy(inherited.id) == ProxyConfig(
        "http", "global.example", 3128, "global-user", "global-pass"
    )
    assert repo.get_effective_proxy(custom.id) == ProxyConfig(
        "socks5", "custom.example", 1080, "custom-user", "custom-pass"
    )
    assert repo.get_effective_proxy(direct.id) is None

    repo.update_proxy_settings(proxy_enabled=False)
    assert repo.get_effective_proxy(inherited.id) is None


def test_default_manager_factories_pass_effective_proxy_to_both_workers(repository, monkeypatch):
    repo, settings = repository
    task = repo.create_task(
        task_data(proxy_mode="custom", proxy_url="http://proxy-user:proxy-pass@proxy.example:8080")
    )
    received = []

    class FakeClient:
        def __init__(self, dsn, proxy):
            received.append((dsn, proxy))

    class FakeWorker:
        def __init__(self, task, **kwargs):
            self.task = task
            self.client_factory = kwargs["client_factory"]

    monkeypatch.setattr("nocix_fucker.client.Client", FakeClient)
    monkeypatch.setattr("backend.app.manager.CheckoutWorker", FakeWorker)
    manager = TaskManager(repo, settings=settings)

    checkout = manager._default_worker_factory(task, threading.Event(), threading.Event())
    check = manager._default_check_factory(task, threading.Event(), threading.Event())
    checkout.client_factory()
    check.client_factory()

    assert received == [
        (
            settings.browser_dsn,
            ProxyConfig("http", "proxy.example", 8080, "proxy-user", "proxy-pass"),
        ),
        (
            settings.browser_dsn,
            ProxyConfig("http", "proxy.example", 8080, "proxy-user", "proxy-pass"),
        ),
    ]


@pytest.mark.parametrize(
    "proxy, expected",
    [
        (
            ProxyConfig("http", "proxy.example", 8080),
            {"proxyType": "manual", "httpProxy": "proxy.example:8080", "sslProxy": "proxy.example:8080"},
        ),
        (
            ProxyConfig("socks5", "proxy.example", 1080, "user", "pass"),
            {
                "proxyType": "manual",
                "socksProxy": "proxy.example:1080",
                "socksVersion": 5,
                "socksUsername": "user",
                "socksPassword": "pass",
            },
        ),
        (
            ProxyConfig("http", "2001:4860:4860::8888", 3128),
            {
                "proxyType": "manual",
                "httpProxy": "[2001:4860:4860::8888]:3128",
                "sslProxy": "[2001:4860:4860::8888]:3128",
            },
        ),
        (
            ProxyConfig("socks5", "2001:4860:4860::8888", 1080, "user", "pass"),
            {
                "proxyType": "manual",
                "socksProxy": "[2001:4860:4860::8888]:1080",
                "socksVersion": 5,
                "socksUsername": "user",
                "socksPassword": "pass",
            },
        ),
    ],
)
def test_proxy_capabilities_map_http_and_socks5_without_url(proxy, expected):
    assert proxy_capabilities(proxy) == expected


def test_http_auth_artifact_is_cleaned_when_extension_install_fails(monkeypatch, tmp_path):
    created = []

    class Options:
        capabilities = {}

        def add_extension(self, path):
            created.append(Path(path).parent)
            assert Path(path).exists()
            raise RuntimeError("extension rejected")

    monkeypatch.setattr("nocix_fucker.client.webdriver.FirefoxOptions", Options)

    with pytest.raises(ProxyInitializationError, match="HTTP proxy authentication"):
        Client(
            "http://browser",
            ProxyConfig("http", "proxy.example", 8080, "user", "password"),
        )

    assert created
    assert all(not path.exists() for path in created)


def test_http_auth_extension_background_script_is_valid_javascript():
    extension_dir = _create_http_auth_extension('user"\\\n', "pass'\\\n")
    try:
        with zipfile.ZipFile(extension_dir / "proxy-auth.xpi") as archive:
            background = archive.read("background.js").decode("utf-8")
        background_path = extension_dir / "background.js"
        background_path.write_text(background, encoding="utf-8")
        node = shutil.which("node")
        if node:
            result = subprocess.run(
                [node, "--check", str(background_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        else:
            assert background.count("{") == background.count("}")
            assert "onAuthRequired.addListener(function(details)" in background
            assert background.endswith('["blocking"]);')
    finally:
        shutil.rmtree(extension_dir, ignore_errors=True)


def test_http_auth_artifact_is_cleaned_after_driver_setup_failure(monkeypatch):
    artifacts = []

    class Options:
        capabilities = {}

        def add_extension(self, path):
            artifacts.append(Path(path).parent)

    class Driver:
        def maximize_window(self):
            raise RuntimeError("maximize failed")

        def quit(self):
            pass

    monkeypatch.setattr("nocix_fucker.client.webdriver.FirefoxOptions", Options)
    monkeypatch.setattr("nocix_fucker.client.webdriver.Remote", lambda **kwargs: Driver())

    with pytest.raises(ProxyInitializationError, match="proxy browser initialization"):
        Client(
            "http://browser",
            ProxyConfig("http", "proxy.example", 8080, "user", "password"),
        )

    assert artifacts
    assert all(not path.exists() for path in artifacts)


def test_http_auth_artifact_is_cleaned_on_normal_client_close(monkeypatch):
    artifacts = []

    class Options:
        capabilities = {}

        def add_extension(self, path):
            artifacts.append(Path(path).parent)

    class Driver:
        def maximize_window(self):
            pass

        def quit(self):
            pass

    monkeypatch.setattr("nocix_fucker.client.webdriver.FirefoxOptions", Options)
    monkeypatch.setattr("nocix_fucker.client.webdriver.Remote", lambda **kwargs: Driver())

    client = Client(
        "http://browser",
        ProxyConfig("http", "proxy.example", 8080, "user", "password"),
    )
    assert artifacts and all(path.exists() for path in artifacts)

    client.close()

    assert all(not path.exists() for path in artifacts)


def test_proxy_initialization_failure_is_pre_order_and_logged(repository):
    repo, _ = repository
    task = repo.create_task(task_data())
    statuses = []

    class FailingClientFactory:
        def __call__(self):
            raise ProxyInitializationError("proxy initialization failed for http://proxy.example:8080")

    from backend.app.worker import CheckoutWorker

    worker = CheckoutWorker(
        task,
        client_factory=FailingClientFactory(),
        repository=repo,
        logger=lambda level, message: statuses.append((level, message)),
    )
    worker.run()

    assert repo.get_task(task.id).status == "failed"
    assert any(level == "ERROR" for level, _ in statuses)
    assert repo.list_task_orders(task.id) == []
    assert all("proxy-user" not in message for _, message in statuses)


def test_single_check_proxy_initialization_failure_is_logged_without_order(repository):
    repo, _ = repository
    task = repo.create_task(task_data())

    class FailingClientFactory:
        def __call__(self):
            raise ProxyInitializationError("proxy initialization failed for http://proxy.example:8080")

    from backend.app.manager import SingleCheckWorker

    worker = SingleCheckWorker(
        task,
        client_factory=FailingClientFactory(),
        repository=repo,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
    )
    worker.run()

    assert repo.get_task(task.id).status == "failed"
    assert repo.list_task_orders(task.id) == []
    logs = repo.list_logs(task.id, None, 10)
    assert any(log.level == "ERROR" for log in logs)


def test_proxy_test_endpoint_requires_key_and_returns_safe_proxy_result(repository, monkeypatch):
    repo, settings = repository
    repo.update_proxy_settings(
        proxy_enabled=True,
        proxy_url="http://endpoint-user:endpoint-pass@proxy.example:8080",
    )
    app = create_app(settings=settings)

    class FakeClient:
        def test_connection(self, url):
            assert url.startswith("https://")

        def close(self):
            pass

    async def exercise():
        async with app.router.lifespan_context(app):
            app.state.proxy_test_client_factory = lambda proxy: FakeClient()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                unauthorized = await client.post("/api/proxy/test")
                response = await client.post(
                    "/api/proxy/test", headers={"X-API-Key": "test-api-key"}
                )
                return unauthorized, response

    unauthorized, response = asyncio.run(exercise())
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["proxy"] == "http://proxy.example:8080"
    assert "endpoint-user" not in response.text
    assert "endpoint-pass" not in response.text


def test_proxy_test_endpoint_reports_direct_connection_without_global_proxy(repository):
    _, settings = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/api/proxy/test", headers={"X-API-Key": "test-api-key"}
                )

    response = asyncio.run(exercise())
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "proxy": "direct",
        "message": "No proxy configured; direct connection selected.",
    }


def test_proxy_test_endpoint_converts_repository_failures_to_safe_response(repository):
    _, settings = repository
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            app.state.repository.get_global_proxy = lambda: (_ for _ in ()).throw(
                RuntimeError("decrypted proxy secret")
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/api/proxy/test", headers={"X-API-Key": "test-api-key"}
                )

    response = asyncio.run(exercise())
    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "proxy": "direct",
        "message": "Proxy test unavailable; direct connection selected.",
    }
    assert "decrypted proxy secret" not in response.text


def test_proxy_test_endpoint_tests_draft_without_persisting_or_returning_credentials(repository):
    repo, settings = repository
    repo.update_proxy_settings(
        proxy_enabled=True,
        proxy_url="http://global-user:global-pass@global.example:3128",
    )
    app = create_app(settings=settings)
    received = []

    class FakeClient:
        def test_connection(self, url):
            assert url == "https://example.com/"

        def close(self):
            pass

    async def exercise():
        async with app.router.lifespan_context(app):
            app.state.proxy_test_client_factory = lambda proxy: (
                received.append(proxy) or FakeClient()
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/proxy/test",
                    headers={"X-API-Key": "test-api-key"},
                    json={
                        "proxy_url": "socks5://draft-user:draft-pass@draft.example:1080"
                    },
                )
        return response

    response = asyncio.run(exercise())
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "proxy": "socks5://draft.example:1080",
        "message": "Proxy connection successful.",
    }
    assert received == [
        ProxyConfig("socks5", "draft.example", 1080, "draft-user", "draft-pass")
    ]
    assert repo.get_global_proxy() == ProxyConfig(
        "http", "global.example", 3128, "global-user", "global-pass"
    )
    assert "draft-user" not in response.text
    assert "draft-pass" not in response.text


def test_proxy_test_endpoint_rejects_invalid_draft_without_echoing_it(repository):
    _, settings = repository
    app = create_app(settings=settings)
    invalid = "http://draft-user:draft%ZZpass@draft.example:8080"

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/api/proxy/test",
                    headers={"X-API-Key": "test-api-key"},
                    json={"proxy_url": invalid},
                )

    response = asyncio.run(exercise())
    assert response.status_code == 422
    assert invalid not in response.text
    assert "draft%ZZpass" not in response.text
