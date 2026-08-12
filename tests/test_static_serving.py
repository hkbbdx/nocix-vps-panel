import asyncio
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from backend.app.config import Settings
from backend.app.main import create_app


def test_health_protected_api_and_spa_routes(monkeypatch, tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('panel')", encoding="utf-8")
    monkeypatch.setattr("backend.app.main.STATIC_DIR", static_dir)

    settings = Settings(
        api_key="test-api-key",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        data_dir=str(tmp_path / "data"),
    )
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await asyncio.gather(
                    client.get("/api/health"),
                    client.get("/api/tasks"),
                    client.get("/"),
                    client.get("/tasks"),
                    client.get("/assets/app.js"),
                    client.get("/api/does-not-exist"),
                )

    health, protected, root, client_route, asset, unknown_api = asyncio.run(exercise())

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert protected.status_code == 401
    assert root.status_code == 200
    assert root.text == "<html>panel</html>"
    assert client_route.status_code == 200
    assert client_route.text == root.text
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert unknown_api.status_code == 404


def test_compose_publishes_only_api_port():
    compose = Path(__file__).parents[1].joinpath("docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert '"8000:8000"' in compose
    assert "4444:4444" not in compose
    assert "5900:5900" not in compose


def test_compose_sets_shanghai_timezone_for_api_and_browser():
    compose = Path(__file__).parents[1].joinpath("docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert compose.count("TZ=Asia/Shanghai") == 2


def test_api_image_bootstraps_bind_mount_before_dropping_privileges():
    dockerfile = Path(__file__).parents[1].joinpath("Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "chown appuser:appuser /app/data" in dockerfile
    assert "gosu appuser uvicorn app.main:app" in dockerfile
    assert '"/usr/local/bin/docker-entrypoint.sh"' in dockerfile


def test_production_port_contract_is_fixed_and_telegram_is_panel_only():
    dockerfile = Path(__file__).parents[1].joinpath("Dockerfile").read_text(
        encoding="utf-8"
    )
    env_example = Path(__file__).parents[1].joinpath(".env.example").read_text(
        encoding="utf-8"
    )
    readme = Path(__file__).parents[1].joinpath("README.md").read_text(
        encoding="utf-8"
    )

    assert '"${HOST:-0.0.0.0}"' in dockerfile
    assert '--port 8000' in dockerfile
    assert 'PORT' not in dockerfile
    assert 'PORT=' not in env_example
    assert 'PORT' not in readme
    assert 'port 8000' in readme
    assert '"${LOG_LEVEL:-info}"' in dockerfile
    assert "TELEGRAM_BOT_TOKEN" not in env_example
    assert "TELEGRAM_CHAT_ID" not in env_example
    assert "authenticated panel" in readme


def test_lifespan_disposes_engine_after_manager_shutdown(monkeypatch, tmp_path):
    import backend.app.main as main_module

    events = []

    class FakeEngine:
        def dispose(self):
            events.append("engine-dispose")

    class FakeRepository:
        def __init__(self, session_factory, settings):
            pass

    class FakeNotifier:
        def __init__(self, repository, settings):
            pass

    class FakeManager:
        def __init__(self, repository, *, settings, worker_factory):
            pass

        async def recover_stale_tasks(self):
            events.append("recover")

        async def shutdown(self):
            events.append("manager-shutdown")

        def owned_worker_count(self):
            events.append("owned-worker-check")
            return 0

    monkeypatch.setattr(main_module, "create_engine", lambda settings: FakeEngine())
    monkeypatch.setattr(main_module, "init_db", lambda engine: events.append("init-db"))
    monkeypatch.setattr(
        main_module, "create_session_factory", lambda engine: lambda: None
    )
    monkeypatch.setattr(main_module, "Repository", FakeRepository)
    monkeypatch.setattr(main_module, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(main_module, "TaskManager", FakeManager)

    settings = Settings(
        api_key="test-api-key",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        data_dir=str(tmp_path / "data"),
    )
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(exercise())

    assert events[-3:] == ["manager-shutdown", "owned-worker-check", "engine-dispose"]


def test_lifespan_keeps_engine_when_manager_retains_worker(monkeypatch, tmp_path, caplog):
    import backend.app.main as main_module

    events = []

    class FakeEngine:
        def dispose(self):
            events.append("engine-dispose")

    class FakeRepository:
        def __init__(self, session_factory, settings):
            pass

    class FakeNotifier:
        def __init__(self, repository, settings):
            pass

    class FakeManager:
        def __init__(self, repository, *, settings, worker_factory):
            pass

        async def recover_stale_tasks(self):
            pass

        async def shutdown(self):
            events.append("manager-shutdown")

        def owned_worker_count(self):
            return 1

    monkeypatch.setattr(main_module, "create_engine", lambda settings: FakeEngine())
    monkeypatch.setattr(main_module, "init_db", lambda engine: None)
    monkeypatch.setattr(
        main_module, "create_session_factory", lambda engine: lambda: None
    )
    monkeypatch.setattr(main_module, "Repository", FakeRepository)
    monkeypatch.setattr(main_module, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(main_module, "TaskManager", FakeManager)

    settings = Settings(
        api_key="test-api-key",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        data_dir=str(tmp_path / "data"),
    )
    app = create_app(settings=settings)

    async def exercise():
        async with app.router.lifespan_context(app):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(exercise())

    assert events == ["manager-shutdown"]
    assert "Keeping SQLite engine alive" in caplog.text
