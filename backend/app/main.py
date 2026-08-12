from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .db import create_engine, create_session_factory, init_db
from .manager import TaskManager
from .repositories import Repository
from .routers import logs, orders, settings as settings_router, stats, tasks
from .telegram import TelegramNotifier
from .worker import CheckoutWorker


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    logging.basicConfig(level=getattr(logging, runtime_settings.log_level, logging.INFO))
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(runtime_settings)
        init_db(engine)
        repository = Repository(create_session_factory(engine), runtime_settings)
        notifier = TelegramNotifier(repository, runtime_settings)
        worker_factory = getattr(app.state, "worker_factory", None)
        if worker_factory is None:
            from nocix_fucker.client import Client

            def worker_factory(task, stop_event, pause_event):
                return CheckoutWorker(
                    task,
                    client_factory=lambda: Client(runtime_settings.browser_dsn, None),
                    repository=repository,
                    stop_event=stop_event,
                    pause_event=pause_event,
                    logger=lambda level, message: repository.append_log(level, task.id, message),
                    notifier=notifier,
                )

        manager = TaskManager(
            repository,
            settings=runtime_settings,
            worker_factory=worker_factory,
        )
        app.state.engine = engine
        app.state.settings = runtime_settings
        app.state.repository = repository
        app.state.telegram_notifier = notifier
        app.state.manager = manager
        await manager.recover_stale_tasks()
        try:
            yield
        finally:
            await manager.shutdown()
            remaining_workers = manager.owned_worker_count()
            if remaining_workers:
                logger.warning(
                    "Keeping SQLite engine alive because %d worker handle(s) "
                    "remain after bounded shutdown",
                    remaining_workers,
                )
            else:
                engine.dispose()

    app = FastAPI(title="NOCIX VPS Panel API", lifespan=lifespan)
    app.dependency_overrides[get_settings] = lambda: runtime_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    app.include_router(tasks.router)
    app.include_router(orders.router)
    app.include_router(logs.router)
    app.include_router(settings_router.router)
    app.include_router(settings_router.telegram_router)
    app.include_router(stats.router)

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_spa(path: str):
        # Unknown API paths must remain API 404s, never become HTML responses.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        static_root = STATIC_DIR.resolve()
        requested = (static_root / path).resolve()
        try:
            requested.relative_to(static_root)
        except ValueError:
            requested = None
        if requested is not None and path and requested.is_file():
            return FileResponse(requested)

        index = static_root / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend build not found")

    return app


app = create_app()
