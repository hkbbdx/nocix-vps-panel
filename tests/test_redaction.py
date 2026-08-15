import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.app.config import Settings
from backend.app.db import create_engine, create_session_factory, init_db
from backend.app.models import Log, Order, Setting, Task
from backend.app.repositories import Repository
from backend.app.schemas import TaskCreate, TaskUpdate
from backend.app.redaction import REDACTION_MARKER, redact_message


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
    settings = Settings(data_dir=str(tmp_path), data_encryption_key=key)
    engine = create_engine(settings, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    try:
        yield Repository(create_session_factory(engine), settings), engine, key
    finally:
        engine.dispose()


def test_task_password_is_encrypted_and_public_record_is_safe(repository):
    repo, engine, key = repository
    task = repo.create_task(task_data())

    assert task.password_configured is True
    assert "plain-password" not in repr(task)
    assert "password" not in task.to_dict()

    with repo.session_factory() as session:
        stored = session.get(Task, task.id)
        assert stored.password_ciphertext != "plain-password"
        assert "plain-password" not in repr(stored)

    assert repo.get_decrypted_password(task.id) == "plain-password"
    assert repo.get_decrypted_password(task.id) == repo.decrypt_password(
        stored.password_ciphertext, key
    )


def test_task_update_and_status_are_persisted(repository):
    repo, _, _ = repository
    created = repo.create_task(task_data())

    updated = repo.update_task(
        created.id,
        TaskUpdate(target_price=72, operating_system="ubuntu", password="new-secret"),
    )
    assert updated.target_price == 72
    assert updated.operating_system == "ubuntu"
    assert repo.get_decrypted_password(created.id) == "new-secret"

    status = repo.set_task_status(created.id, "failed", error="checkout failed")
    assert status.status == "failed"
    assert status.last_error == "checkout failed"
    assert repo.get_task(created.id).status == "failed"


def test_order_and_log_listing_filters_and_limits(repository):
    repo, _, _ = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="other-password"))

    repo.create_order(first.id, "failed", "72.00", "price mismatch")
    repo.create_order(second.id, "success", None, None)
    repo.append_log("INFO", first.id, "password=plain-password token=abc123")
    repo.append_log("ERROR", first.id, "session_id=session-secret")
    repo.append_log("INFO", second.id, "unrelated")

    assert [order.task_id for order in repo.list_orders()] == [first.id, second.id]
    assert len(repo.list_logs(first.id, "INFO", 1)) == 1
    assert repo.list_logs(first.id, "INFO", 1)[0].message == (
        f"password={REDACTION_MARKER} token={REDACTION_MARKER}"
    )
    assert repo.list_logs(None, None, 2)[0].message == "unrelated"


def test_redaction_covers_sensitive_key_value_forms():
    message = (
        'password="pw" cc_num=4111111111111111 '
        "cc_ccv:'123' cc_exp_month=01 cc_exp_year=2030 "
        'token="tok-value" cookie=cookie-value authorization=Bearer%20auth '
        'paypal_token=paypal-secret session_id=session-secret '
        'paypal_secret="paypal-secret-2" session_cookie=session-cookie'
    )

    redacted = redact_message(message)

    assert all(secret not in redacted for secret in (
        "pw", "4111111111111111", "123", "01", "2030", "tok-value",
        "cookie-value", "Bearer%20auth", "tok-value", "paypal-secret", "session-secret",
        "paypal-secret-2", "session-cookie",
    ))
    assert redacted.count(REDACTION_MARKER) == 12


def test_redaction_hides_raw_at_proxy_passwords_without_leaking_the_suffix():
    raw = "http://proxy-user:raw@secret@proxy.example:8080"
    redacted = redact_message(f"proxy failed at {raw}")

    assert "raw@secret" not in redacted
    assert "proxy-user" not in redacted
    assert "proxy.example:8080" in redacted


def test_redaction_covers_json_like_payloads():
    message = (
        '{"password":"pw","cc_num":"4111","cc_ccv":"123",'
        '"cc_exp_month":"01","cc_exp_year":"2030",'
        '"token":"secret-token-value","cookie":"cookie-value",'
        '"authorization":"Bearer auth","paypal_session":"paypal-session",'
        '"session_secret":"session-secret"}'
    )

    redacted = redact_message(message)

    assert all(secret not in redacted for secret in (
        "pw", "4111", "123", "01", "2030", "secret-token-value", "cookie-value",
        "Bearer auth", "paypal-session", "session-secret",
    ))
    assert redacted.count(REDACTION_MARKER) == 10


def test_redaction_covers_representative_credential_aliases():
    message = (
        '"access_token":"access-secret" api_key=api-secret '
        'REFRESH_TOKEN="refresh-secret" client_secret=client-secret '
        'client_secret_key="client-key-secret" secret_key=signing-secret '
        'bot_token=bot-secret session_token="session-token-secret" '
        'auth_token=auth-secret private_key="private-key-secret"'
    )

    redacted = redact_message(message)

    assert all(secret not in redacted for secret in (
        "access-secret",
        "api-secret",
        "refresh-secret",
        "client-secret",
        "client-key-secret",
        "signing-secret",
        "bot-secret",
        "session-token-secret",
        "auth-secret",
        "private-key-secret",
    ))
    assert redacted.count(REDACTION_MARKER) == 10


def test_redaction_covers_generic_card_aliases_in_json_and_key_value_forms():
    aliases = [
        "card",
        "card_number",
        "card_no",
        "card_cvv",
        "cvv",
        "cvc",
        "security_code",
        "card_expiry",
        "card_exp_month",
        "card_exp_year",
        "expiry",
        "expiration",
    ]
    json_payload = "{" + ",".join(
        f'"{alias}":"CARDSECRET_{index:02d}"'
        for index, alias in enumerate(aliases)
    ) + "}"
    key_value_payload = " ".join(
        f"{alias.upper()}=CARDSECRET_{index:02d}"
        for index, alias in enumerate(aliases, start=len(aliases))
    )

    redacted = redact_message(f"{json_payload} {key_value_payload}")

    assert all(
        f"CARDSECRET_{index:02d}" not in redacted
        for index in range(len(aliases) * 2)
    )
    assert redacted.count(REDACTION_MARKER) == len(aliases) * 2


def test_redaction_removes_complete_escaped_json_secret_value():
    message = (
        r'{"password":"secret with \"quoted\" text and \\slashes",'
        r'"safe":"preserve this"}'
    )

    redacted = redact_message(message)

    assert "secret with" not in redacted
    assert "quoted" not in redacted
    assert "slashes" not in redacted
    assert r'"safe":"preserve this"' in redacted
    assert redacted.count(REDACTION_MARKER) == 1


def test_init_db_creates_all_persistence_tables(repository):
    _, engine, _ = repository

    assert set(inspect(engine).get_table_names()) >= {
        Task.__tablename__,
        Order.__tablename__,
        Log.__tablename__,
        Setting.__tablename__,
    }


def test_sqlite_connection_pragmas_are_configured(repository):
    _, engine, _ = repository

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"


def test_list_tasks_returns_tasks_in_creation_order(repository):
    repo, _, _ = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="second-password"))

    assert [task.id for task in repo.list_tasks()] == [first.id, second.id]


def test_list_logs_clamps_limit_to_zero_and_maximum(repository):
    repo, _, _ = repository
    for index in range(501):
        repo.append_log("INFO", None, f"message-{index}")

    assert repo.list_logs(None, None, -1) == []
    assert len(repo.list_logs(None, None, 9999)) == 500


def test_missing_task_operations_have_explicit_behavior(repository):
    repo, _, _ = repository
    missing_id = "missing-task"

    assert repo.get_task(missing_id) is None
    with pytest.raises(KeyError):
        repo.update_task(missing_id, TaskUpdate(target_price=70))
    with pytest.raises(KeyError):
        repo.set_task_status(missing_id, "failed")
    with pytest.raises(KeyError):
        repo.get_decrypted_password(missing_id)


def test_repository_rejects_invalid_fernet_key(repository):
    _, engine, _ = repository
    settings = Settings(data_encryption_key="not-a-fernet-key")

    with pytest.raises(ValueError, match="DATA_ENCRYPTION_KEY must be a valid Fernet key"):
        Repository(create_session_factory(engine), settings)


def test_related_records_cascade_on_task_delete(repository):
    repo, _, _ = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="other-password"))
    repo.create_order(first.id, "failed", "72.00", "first task")
    repo.create_order(second.id, "success", "59.00", None)
    repo.append_log("INFO", first.id, "first task")
    repo.append_log("INFO", second.id, "second task")

    repo.delete_task(first.id)

    assert [order.task_id for order in repo.list_orders()] == [second.id]
    assert [log.task_id for log in repo.list_logs(first.id, None, 10)] == []
    assert [log.task_id for log in repo.list_logs(second.id, None, 10)] == [second.id]


def test_related_records_require_existing_task(repository):
    repo, _, _ = repository

    with pytest.raises(IntegrityError):
        repo.create_order("missing-task", "failed", None, "missing")
    with pytest.raises(IntegrityError):
        repo.append_log("ERROR", "missing-task", "missing")


def test_direct_session_task_delete_cascades_related_records(repository):
    repo, _, _ = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="other-password"))
    repo.create_order(first.id, "failed", "72.00", "first task")
    repo.create_order(second.id, "success", "59.00", None)
    repo.append_log("INFO", first.id, "first task")
    repo.append_log("INFO", second.id, "second task")

    with repo.session_factory() as session:
        session.delete(session.get(Task, first.id))
        session.commit()

    assert [order.task_id for order in repo.list_orders()] == [second.id]
    assert repo.list_logs(first.id, None, 10) == []
    assert [log.task_id for log in repo.list_logs(second.id, None, 10)] == [second.id]


def test_deleting_task_keeps_unrelated_records(repository):
    repo, _, _ = repository
    first = repo.create_task(task_data())
    second = repo.create_task(task_data(password="other-password"))
    repo.create_order(second.id, "success", "59.00", None)
    repo.append_log("INFO", second.id, "unrelated")

    repo.delete_task(first.id)

    assert repo.get_task(first.id) is None
    assert repo.get_task(second.id) is not None
    assert len(repo.list_orders()) == 1
    assert len(repo.list_logs(second.id, None, 10)) == 1
