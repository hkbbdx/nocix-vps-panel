import sqlite3

from sqlalchemy import inspect, text

from backend.app.db import create_engine, init_db


def test_init_db_upgrades_legacy_sqlite_without_losing_task_data(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE tasks (
            id VARCHAR(64) PRIMARY KEY,
            goods_id VARCHAR(64) NOT NULL,
            stock_url VARCHAR(2048) NOT NULL,
            cart_url VARCHAR(2048) NOT NULL,
            target_price FLOAT NOT NULL,
            wait_interval FLOAT NOT NULL,
            operating_system VARCHAR(32) NOT NULL,
            email VARCHAR(320) NOT NULL,
            password_ciphertext TEXT NOT NULL,
            new_customer BOOLEAN NOT NULL,
            payment_method VARCHAR(32) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL
        );
        INSERT INTO tasks VALUES (
            'legacy-task', '418', 'https://nocix.net/stock',
            'https://nocix.net/cart', 59.0, 5.0, 'debian',
            'buyer@example.com', 'ciphertext', 0, 'paypal',
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
    order_columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    with engine.connect() as connection:
        task = connection.execute(
            text("SELECT goods_id, auto_submit, status, running_before_shutdown FROM tasks WHERE id = 'legacy-task'")
        ).one()
        version = connection.execute(text("SELECT version FROM schema_version")).scalar_one()

    assert {"status", "running_before_shutdown", "last_error"} <= columns
    assert "observed_price" in order_columns
    assert task.goods_id == "418"
    assert task.auto_submit == 1
    assert task.status == "stopped"
    assert task.running_before_shutdown == 0
    assert version >= 1
