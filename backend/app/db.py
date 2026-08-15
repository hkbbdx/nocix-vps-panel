from pathlib import Path
from typing import Callable

from sqlalchemy import Engine, create_engine as sqlalchemy_create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_engine(settings=None, database_url: str | None = None) -> Engine:
    if database_url is None:
        if settings is None:
            raise ValueError("settings or database_url is required")
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{data_dir / 'nocix.db'}"

    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 5} if is_sqlite else {}
    engine = sqlalchemy_create_engine(database_url, connect_args=connect_args)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        return

    migrations = {
        "tasks": {
            "auto_submit": "BOOLEAN NOT NULL DEFAULT 1",
            "status": "VARCHAR(32) NOT NULL DEFAULT 'stopped'",
            "last_stock_status": "VARCHAR(32)",
            "last_checked_at": "DATETIME",
            "last_error": "TEXT",
            "running_before_shutdown": "BOOLEAN NOT NULL DEFAULT 0",
            "proxy_mode": "VARCHAR(16) NOT NULL DEFAULT 'inherit'",
            "proxy_url_ciphertext": "TEXT",
        },
        "orders": {
            "observed_price": "VARCHAR(128)",
            "error": "TEXT",
            "created_at": "DATETIME",
        },
        "logs": {"created_at": "DATETIME"},
        "settings": {
            "updated_at": "DATETIME",
            "proxy_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "proxy_url_ciphertext": "TEXT",
        },
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL)"
            )
        )
        version = connection.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
        if version is None:
            connection.execute(text("INSERT INTO schema_version (version) VALUES (0)"))
        existing_tables = set(inspect(connection).get_table_names())
        for table, columns in migrations.items():
            if table not in existing_tables:
                continue
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
                    )
        connection.execute(text("UPDATE tasks SET auto_submit = 1 WHERE auto_submit != 1"))
        connection.execute(
            text("UPDATE tasks SET proxy_mode = 'inherit' WHERE proxy_mode IS NULL")
        )
        connection.execute(text("UPDATE schema_version SET version = 1"))


create_all = init_db
