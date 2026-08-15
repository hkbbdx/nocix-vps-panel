import asyncio
import sqlite3

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import inspect, text

from backend.app.config import Settings
from backend.app.db import create_engine, create_session_factory, init_db
from backend.app.main import create_app
from backend.app.models import Setting, Task
from backend.app.proxy import ProxyValidationError, parse_proxy_url
from backend.app.repositories import Repository
from backend.app.redaction import REDACTION_MARKER
from backend.app.schemas import SettingsUpdate, TaskCreate, TaskUpdate


def task_data(**overrides):
    data = {
        "goods_id": "418",
        "target_price": 59,
        "wait_interval": 5,
        "email": "buyer@example.com",
        "password": "task-password",
    }
    data.update(overrides)
    return data


@pytest.fixture
def repository(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        api_key="test-api-key",
        data_dir=str(tmp_path),
        data_encryption_key=key,
    )
    engine = create_engine(settings, database_url=f"sqlite:///{tmp_path / 'proxy.db'}")
    init_db(engine)
    try:
        yield Repository(create_session_factory(engine), settings), engine, key
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "value, scheme, host, port, username, password",
    [
        ("http://proxy.example:8080", "http", "proxy.example", 8080, None, None),
        (
            "socks5://user%40name:p%3Ass@proxy.example:1080",
            "socks5",
            "proxy.example",
            1080,
            "user@name",
            "p:ss",
        ),
        (
            "http://user:password@[2001:4860:4860::8888]:3128",
            "http",
            "2001:4860:4860::8888",
            3128,
            "user",
            "password",
        ),
        (
            "http://user:pa%40ss@proxy.example:3128",
            "http",
            "proxy.example",
            3128,
            "user",
            "pa@ss",
        ),
    ],
)
def test_parse_proxy_url_accepts_supported_forms(
    value, scheme, host, port, username, password
):
    config = parse_proxy_url(value)

    assert (config.scheme, config.host, config.port) == (scheme, host, port)
    assert (config.username, config.password) == (username, password)
    assert config.safe_display == f"{scheme}://{'[' + host + ']' if ':' in host else host}:{port}"
    assert "password" not in config.safe_display
    assert "user" not in config.safe_display


@pytest.mark.parametrize(
    "value",
    [
        "ftp://proxy.example:8080",
        "socks4://proxy.example:1080",
        "http://proxy.example",
        "http://proxy.example:0",
        "http://proxy.example:65536",
        "http://proxy.example:8080?secret=value",
        "http://proxy.example:8080#secret",
        "http://proxy.example:8080/path",
        "http://proxy.example:8080/",
        "http://proxy.example:8080 with-space",
        "http://user@proxy.example:8080",
        "http://:password@proxy.example:8080",
        "http://user:@proxy.example:8080",
        "http://user%ZZ:password@proxy.example:8080",
        "http://user:pass%2@proxy.example:8080",
        "http://user:pa@ss@proxy.example:8080",
        "http://proxy%ZZ.example:8080",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://10.0.0.1:8080",
        "http://169.254.169.254:8080",
        "http://[::1]:8080",
    ],
)
def test_parse_proxy_url_rejects_unsafe_or_malformed_forms(value):
    with pytest.raises(ProxyValidationError) as exc_info:
        parse_proxy_url(value)

    assert value not in str(exc_info.value)
    assert "password" not in str(exc_info.value)


def test_proxy_hosts_are_not_restricted_to_nocix_domains():
    assert parse_proxy_url("http://public-proxy.example:3128").host == "public-proxy.example"


def test_task_proxy_modes_validate_without_changing_auto_submit():
    assert TaskCreate(**task_data()).proxy_mode == "inherit"
    custom = TaskCreate(**task_data(proxy_mode="custom", proxy_url="http://proxy.example:8080"))
    assert custom.proxy_mode == "custom"
    assert custom.auto_submit is True
    assert TaskCreate(**task_data(proxy_mode="direct")).proxy_url is None

    with pytest.raises(ValidationError):
        TaskCreate(**task_data(proxy_mode="custom"))
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(proxy_mode="direct", proxy_url="http://proxy.example:8080"))
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(proxy_url="http://proxy.example:8080"))
    with pytest.raises(ValidationError):
        TaskUpdate(proxy_mode="inherit", proxy_url="http://proxy.example:8080")
    with pytest.raises(ValidationError):
        TaskUpdate(proxy_mode="custom")


def test_task_proxy_urls_are_encrypted_and_worker_only(repository):
    repo, engine, key = repository
    created = repo.create_task(
        TaskCreate(**task_data(proxy_mode="custom", proxy_url="http://user:secret@proxy.example:8080"))
    )

    assert created.proxy_mode == "custom"
    assert created.proxy_configured is True
    assert "proxy_url" not in created.to_dict()
    assert "secret" not in repr(created)
    with repo.session_factory() as session:
        stored = session.get(Task, created.id)
        assert stored.proxy_url_ciphertext
        assert "http://user:secret@proxy.example:8080" not in stored.proxy_url_ciphertext
        assert Fernet(key.encode()).decrypt(stored.proxy_url_ciphertext.encode()).decode() == (
            "http://user:secret@proxy.example:8080"
        )

    assert repo.get_task_proxy_url(created.id) == "http://user:secret@proxy.example:8080"
    updated = repo.update_task(created.id, TaskUpdate(proxy_mode="direct"))
    assert updated.proxy_mode == "direct"
    assert updated.proxy_configured is False
    assert repo.get_task_proxy_url(created.id) is None


def test_global_proxy_snapshot_is_encrypted_and_inheritance_is_atomic(repository):
    repo, _, key = repository
    inherited = repo.create_task(TaskCreate(**task_data()))
    custom = repo.create_task(
        TaskCreate(**task_data(proxy_mode="custom", proxy_url="socks5://custom.example:1080"))
    )
    direct = repo.create_task(TaskCreate(**task_data(proxy_mode="direct")))

    repo.update_proxy_settings(
        proxy_enabled=True,
        proxy_url="http://global-user:global-secret@global.example:3128",
    )
    snapshot = repo.get_proxy_settings()
    assert snapshot == {"proxy_enabled": True, "proxy_configured": True}
    assert repo.get_effective_proxy_url(inherited.id) == (
        "http://global-user:global-secret@global.example:3128"
    )
    assert repo.get_effective_proxy_url(custom.id) == "socks5://custom.example:1080"
    assert repo.get_effective_proxy_url(direct.id) is None

    with repo.session_factory() as session:
        stored = session.get(Setting, "__global__")
        assert stored.proxy_url_ciphertext
        assert Fernet(key.encode()).decrypt(stored.proxy_url_ciphertext.encode()).decode() == (
            "http://global-user:global-secret@global.example:3128"
        )

    repo.update_proxy_settings(proxy_enabled=False)
    assert repo.get_effective_proxy_url(inherited.id) is None
    assert repo.get_proxy_settings() == {"proxy_enabled": False, "proxy_configured": False}
    with repo.session_factory() as session:
        assert session.get(Setting, "__global__").proxy_url_ciphertext is None
    repo.update_proxy_settings(proxy_url=None)
    assert repo.get_proxy_settings()["proxy_configured"] is False


def test_proxy_credentials_and_ciphertexts_are_redacted_from_logs(repository):
    repo, _, _ = repository
    repo.append_log(
        "ERROR",
        None,
        "proxy_url=http://proxy-user:proxy-secret@proxy.example:8080 "
        "proxy_url_ciphertext=encrypted-proxy-value",
    )

    message = repo.list_logs(None, None, 1)[0].message
    assert "proxy-user" not in message
    assert "proxy-secret" not in message
    assert "encrypted-proxy-value" not in message


def test_raw_proxy_urls_are_redacted_through_task_error_and_log_paths(repository):
    repo, _, _ = repository
    task = repo.create_task(TaskCreate(**task_data()))
    raw_http = "http://error-user:error-secret@proxy.example:8080"
    raw_socks = "socks5://log-user:log-secret@proxy.example:1080"

    updated = repo.set_task_status(task.id, "failed", f"browser failed at {raw_http}")
    repo.append_log("ERROR", task.id, f"worker failed at {raw_socks}")

    assert raw_http not in updated.last_error
    assert raw_socks not in repo.list_logs(task.id, None, 1)[0].message
    assert "error-secret" not in updated.last_error
    assert "log-secret" not in repo.list_logs(task.id, None, 1)[0].message
    assert "proxy.example:8080" in updated.last_error
    assert "proxy.example:1080" in repo.list_logs(task.id, None, 1)[0].message
    assert REDACTION_MARKER not in updated.last_error


def test_task_error_api_response_redacts_embedded_proxy_credentials(repository):
    _, engine, key = repository
    settings = Settings(
        api_key="test-api-key",
        data_dir=str(engine.url.database.rsplit("\\", 1)[0]),
        data_encryption_key=key,
    )
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            task = app.state.repository.create_task(TaskCreate(**task_data()))
            app.state.repository.set_task_status(
                task.id,
                "failed",
                "proxy startup failed: http://api-user:api-secret@proxy.example:8080",
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/tasks/{task.id}",
                    headers={"X-API-Key": "test-api-key"},
                )

    response = asyncio.run(exercise())
    assert response.status_code == 200
    body = response.json()
    assert "api-user" not in body["last_error"]
    assert "api-secret" not in body["last_error"]
    assert "proxy.example:8080" in body["last_error"]


@pytest.mark.parametrize(
    "value",
    [
        "http://proxy..example:8080",
        "http://-proxy.example:8080",
        "http://proxy-.example:8080",
        "http://proxy.example-:8080",
        "http://proxy%2eexample:8080",
        "http://127.1:8080",
        "http://2130706433:8080",
        "http://0x7f000001:8080",
        "http://0177.0.0.1:8080",
        "http://proxy\x00.example:8080",
        "http://proxy\n.example:8080",
        "http://代理.example:8080",
        "http://proxy_underscore.example:8080",
    ],
)
def test_parse_proxy_url_rejects_non_dns_hosts_and_ambiguous_ip_aliases(value):
    with pytest.raises(ProxyValidationError):
        parse_proxy_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://proxy.example:8080",
        "socks5://sub.proxy.example:1080",
        "http://proxy1.example-2.test:1",
    ],
)
def test_parse_proxy_url_accepts_ascii_dns_hostnames(value):
    assert parse_proxy_url(value).host


def test_settings_update_is_atomic_when_repository_commit_fails(repository, monkeypatch):
    repo, _, _ = repository
    repo.set_settings({"log_level": "INFO", "telegram_enabled": "false"})
    repo.update_proxy_settings(
        proxy_enabled=False,
        proxy_url="http://old.example:8080",
    )
    original = {
        "log_level": repo.get_setting("log_level"),
        "telegram_enabled": repo.get_setting("telegram_enabled"),
        "proxy": repo.get_proxy_settings(),
    }

    real_session_factory = repo.session_factory

    class FailingSession:
        def __init__(self, session):
            self._session = session

        def __enter__(self):
            self._session.__enter__()
            return self._session

        def __exit__(self, exc_type, exc_value, traceback):
            return self._session.__exit__(exc_type, exc_value, traceback)

    class FailingFactory:
        def __call__(self):
            session = real_session_factory()
            def fail_commit():
                raise RuntimeError("injected settings commit failure")

            session.commit = fail_commit
            return FailingSession(session)

    monkeypatch.setattr(repo, "session_factory", FailingFactory())
    with pytest.raises(RuntimeError, match="injected settings commit failure"):
        repo.set_settings_atomic(
            {"log_level": "DEBUG", "telegram_enabled": "true"},
            proxy_enabled=True,
            proxy_url_ciphertext="new-ciphertext",
        )
    monkeypatch.setattr(repo, "session_factory", real_session_factory)

    assert repo.get_setting("log_level") == original["log_level"]
    assert repo.get_setting("telegram_enabled") == original["telegram_enabled"]
    assert repo.get_proxy_settings() == original["proxy"]


def test_old_database_migration_adds_proxy_columns_and_defaults_inherit(tmp_path):
    database = tmp_path / "legacy-proxy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE tasks (
            id VARCHAR(64) PRIMARY KEY, goods_id VARCHAR(64) NOT NULL,
            stock_url VARCHAR(2048) NOT NULL, cart_url VARCHAR(2048) NOT NULL,
            target_price FLOAT NOT NULL, wait_interval FLOAT NOT NULL,
            operating_system VARCHAR(32) NOT NULL, email VARCHAR(320) NOT NULL,
            password_ciphertext TEXT NOT NULL, new_customer BOOLEAN NOT NULL,
            payment_method VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE settings (key VARCHAR(128) PRIMARY KEY, value_ciphertext TEXT);
        INSERT INTO tasks VALUES (
            'legacy', '418', 'https://nocix.net/stock', 'https://nocix.net/cart',
            59, 5, 'debian', 'buyer@example.com', 'cipher', 0, 'paypal',
            '2026-08-01 00:00:00', '2026-08-01 00:00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    engine = create_engine(database_url=f"sqlite:///{database}")
    init_db(engine)
    init_db(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    settings_columns = {column["name"] for column in inspect(engine).get_columns("settings")}
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT proxy_mode, proxy_url_ciphertext FROM tasks WHERE id = 'legacy'")
        ).one()
    assert {"proxy_mode", "proxy_url_ciphertext"} <= columns
    assert {"proxy_enabled", "proxy_url_ciphertext"} <= settings_columns
    assert row.proxy_mode == "inherit"
    assert row.proxy_url_ciphertext is None
    engine.dispose()


def test_proxy_api_requires_auth_and_redacts_urls(repository):
    _, engine, key = repository
    settings = Settings(
        api_key="test-api-key",
        data_dir=str(engine.url.database.rsplit("\\", 1)[0]),
        data_encryption_key=key,
    )
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                unauthorized = await client.get("/api/settings")
                headers = {"X-API-Key": "test-api-key"}
                configured = await client.put(
                    "/api/settings",
                    headers=headers,
                    json={
                        "proxy_enabled": True,
                        "proxy_url": "http://global-user:global-secret@global.example:3128",
                    },
                )
                created = await client.post(
                    "/api/tasks",
                    headers=headers,
                    json=task_data(
                        proxy_mode="custom",
                        proxy_url="socks5://task-user:task-secret@task.example:1080",
                    ),
                )
                invalid = await client.post(
                    "/api/tasks",
                    headers=headers,
                    json=task_data(
                        proxy_mode="custom",
                        proxy_url="http://user:secret@localhost:8080",
                    ),
                )
                fetched = await client.get("/api/settings", headers=headers)
        return unauthorized, configured, created, invalid, fetched

    unauthorized, configured, created, invalid, fetched = asyncio.run(exercise())
    for response in (configured, created, fetched):
        assert "global-secret" not in response.text
        assert "task-secret" not in response.text
        assert "proxy_url" not in response.text
        assert "proxy_url_ciphertext" not in response.text
    assert unauthorized.status_code == 401
    assert configured.status_code == 200
    assert configured.json()["proxy_enabled"] is True
    assert configured.json()["proxy_configured"] is True
    assert created.status_code == 201
    assert created.json()["proxy_mode"] == "custom"
    assert created.json()["proxy_configured"] is True
    assert created.json()["effective_proxy_configured"] is True
    assert invalid.status_code == 422
    assert "localhost" not in invalid.text
    assert "task-secret" not in invalid.text


def test_settings_update_schema_keeps_existing_settings_and_accepts_proxy_fields():
    settings = SettingsUpdate(
        log_level="DEBUG",
        telegram_enabled=True,
        proxy_enabled=False,
        proxy_url="http://proxy.example:8080",
    )
    assert settings.log_level == "DEBUG"
    assert settings.telegram_enabled is True
    assert settings.proxy_enabled is False
    assert settings.proxy_url == "http://proxy.example:8080"


def test_task_records_report_effective_proxy_configuration(repository):
    repo, _, _ = repository
    inherited = repo.create_task(TaskCreate(**task_data()))
    custom = repo.create_task(
        TaskCreate(**task_data(proxy_mode="custom", proxy_url="http://custom.example:8080"))
    )
    direct = repo.create_task(TaskCreate(**task_data(proxy_mode="direct")))

    repo.update_proxy_settings(proxy_enabled=True, proxy_url="http://global.example:3128")
    records = {record.id: record for record in repo.list_tasks()}
    assert records[inherited.id].effective_proxy_configured is True
    assert records[custom.id].effective_proxy_configured is True
    assert records[direct.id].effective_proxy_configured is False
    assert records[inherited.id].to_dict()["effective_proxy_configured"] is True
