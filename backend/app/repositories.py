from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from .config import Settings
from .models import Log, Order, Setting, Task, utc_now
from .proxy import ProxyConfig, parse_proxy_url
from .redaction import redact_message
from .schemas import TaskCreate, TaskUpdate


_UNSET = object()


@dataclass(frozen=True)
class TaskRecord:
    id: str
    goods_id: str
    stock_url: str
    cart_url: str
    target_price: float
    wait_interval: float
    operating_system: str
    email: str
    new_customer: bool
    payment_method: str
    auto_submit: bool
    proxy_mode: str
    proxy_configured: bool
    effective_proxy_configured: bool
    password_configured: bool
    status: str
    last_stock_status: str | None
    last_checked_at: datetime | None
    last_error: str | None
    running_before_shutdown: bool
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goods_id": self.goods_id,
            "stock_url": self.stock_url,
            "cart_url": self.cart_url,
            "target_price": self.target_price,
            "wait_interval": self.wait_interval,
            "operating_system": self.operating_system,
            "email": self.email,
            "new_customer": self.new_customer,
            "payment_method": self.payment_method,
            "auto_submit": self.auto_submit,
            "proxy_mode": self.proxy_mode,
            "proxy_configured": self.proxy_configured,
            "effective_proxy_configured": self.effective_proxy_configured,
            "password_configured": self.password_configured,
            "status": self.status,
            "last_stock_status": self.last_stock_status,
            "last_checked_at": self.last_checked_at,
            "last_error": self.last_error,
            "running_before_shutdown": self.running_before_shutdown,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class OrderRecord:
    id: int
    task_id: str
    status: str
    observed_price: str | None
    error: str | None
    created_at: datetime


@dataclass(frozen=True)
class LogRecord:
    id: int
    level: str
    task_id: str | None
    message: str
    created_at: datetime


def encrypt_password(password: str, key: str) -> str:
    return Fernet(key.encode("ascii")).encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(ciphertext: str, key: str) -> str:
    return Fernet(key.encode("ascii")).decrypt(ciphertext.encode("ascii")).decode("utf-8")


def encrypt_secret(value: str, key: str) -> str:
    return Fernet(key.encode("ascii")).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, key: str) -> str:
    return Fernet(key.encode("ascii")).decrypt(ciphertext.encode("ascii")).decode("utf-8")


class Repository:
    def __init__(self, session_factory: Callable[[], Session], settings: Settings):
        self.session_factory = session_factory
        self.settings = settings
        self._encryption_key = self._validate_encryption_key()

    def _validate_encryption_key(self) -> str:
        if not self.settings.data_encryption_key:
            raise ValueError("DATA_ENCRYPTION_KEY is required for password storage")
        try:
            Fernet(self.settings.data_encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return self.settings.data_encryption_key

    @staticmethod
    def decrypt_password(ciphertext: str, key: str) -> str:
        return decrypt_password(ciphertext, key)

    def _record(self, task: Task, setting: Setting | None = None) -> TaskRecord:
        if setting is None:
            with self.session_factory() as session:
                setting = session.get(Setting, "__global__")
        proxy_mode = task.proxy_mode or "inherit"
        effective_proxy_configured = (
            bool(task.proxy_url_ciphertext)
            if proxy_mode == "custom"
            else bool(
                proxy_mode == "inherit"
                and setting
                and setting.proxy_enabled
                and setting.proxy_url_ciphertext
            )
        )
        return TaskRecord(
            id=task.id,
            goods_id=task.goods_id,
            stock_url=task.stock_url,
            cart_url=task.cart_url,
            target_price=task.target_price,
            wait_interval=task.wait_interval,
            operating_system=task.operating_system,
            email=task.email,
            new_customer=task.new_customer,
            payment_method=task.payment_method,
            auto_submit=task.auto_submit,
            proxy_mode=proxy_mode,
            proxy_configured=bool(task.proxy_url_ciphertext),
            effective_proxy_configured=effective_proxy_configured,
            password_configured=bool(task.password_ciphertext),
            status=task.status,
            last_stock_status=task.last_stock_status,
            last_checked_at=task.last_checked_at,
            last_error=redact_message(task.last_error) if task.last_error is not None else None,
            running_before_shutdown=task.running_before_shutdown,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    def _order_record(order: Order) -> OrderRecord:
        return OrderRecord(
            id=order.id,
            task_id=order.task_id,
            status=order.status,
            observed_price=order.observed_price,
            error=order.error,
            created_at=order.created_at,
        )

    @staticmethod
    def _log_record(log: Log) -> LogRecord:
        return LogRecord(
            id=log.id,
            level=log.level,
            task_id=log.task_id,
            message=log.message,
            created_at=log.created_at,
        )

    def create_task(self, task: TaskCreate) -> TaskRecord:
        model = Task(
            id=str(uuid4()),
            goods_id=task.goods_id,
            stock_url=task.stock_url,
            cart_url=task.cart_url,
            target_price=task.target_price,
            wait_interval=task.wait_interval,
            operating_system=task.operating_system,
            email=str(task.email),
            password_ciphertext=encrypt_password(task.password, self._encryption_key),
            new_customer=task.new_customer,
            payment_method=task.payment_method,
            auto_submit=True,
            proxy_mode=task.proxy_mode,
            proxy_url_ciphertext=(
                encrypt_secret(task.proxy_url, self._encryption_key)
                if task.proxy_url is not None
                else None
            ),
        )
        with self.session_factory() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._record(model)

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            return self._record(model) if model else None

    def list_tasks(self) -> list[TaskRecord]:
        with self.session_factory() as session:
            models = session.scalars(select(Task).order_by(Task.created_at, Task.id)).all()
            return [self._record(model) for model in models]

    def update_task(self, task_id: str, patch: TaskUpdate) -> TaskRecord:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            values = patch.dict(exclude_unset=True)
            password = values.pop("password", None)
            proxy_url = values.pop("proxy_url", None)
            proxy_mode = values.get("proxy_mode")
            for field, value in values.items():
                if field == "email":
                    value = str(value)
                setattr(model, field, value)
            if password is not None:
                model.password_ciphertext = encrypt_password(password, self._encryption_key)
            if proxy_mode is not None:
                model.proxy_mode = proxy_mode
                model.proxy_url_ciphertext = (
                    encrypt_secret(proxy_url, self._encryption_key)
                    if proxy_mode == "custom" and proxy_url is not None
                    else None
                )
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def delete_task(self, task_id: str) -> None:
        with self.session_factory() as session:
            # Orders and logs are task-owned history; delete them before the task.
            session.execute(delete(Order).where(Order.task_id == task_id))
            session.execute(delete(Log).where(Log.task_id == task_id))
            result = session.execute(delete(Task).where(Task.id == task_id))
            if result.rowcount == 0:
                session.rollback()
                raise KeyError(task_id)
            session.commit()

    def set_task_status(self, task_id: str, status: str, error: str | None = None) -> TaskRecord:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            model.status = status
            if status in {"success", "failed", "unknown", "submitted_pending_confirmation"}:
                model.running_before_shutdown = False
            model.last_error = redact_message(error) if error is not None else None
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def set_running_before_shutdown(self, task_id: str, value: bool) -> TaskRecord:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            model.running_before_shutdown = value
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def set_task_lifecycle(
        self,
        task_id: str,
        status: str,
        *,
        running_before_shutdown: bool,
        error: str | None = None,
    ) -> TaskRecord:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            model.status = status
            model.running_before_shutdown = (
                False
                if status in {"success", "failed", "unknown", "submitted_pending_confirmation"}
                else running_before_shutdown
            )
            model.last_error = redact_message(error) if error is not None else None
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def stop_task(self, task_id: str) -> TaskRecord:
        """Stop only a task that is not already terminal.

        The conditional update makes a concurrent successful submission win over
        a stale stop request, while a stop committed first is visible to the
        worker's atomic submission finalization.
        """
        stoppable_statuses = ("stopped", "running", "checking", "ordering", "paused")
        terminal_statuses = (
            "success",
            "failed",
            "unknown",
            "submitted_pending_confirmation",
        )
        with self.session_factory() as session:
            result = session.execute(
                update(Task)
                .where(Task.id == task_id, Task.status.in_(stoppable_statuses))
                .values(
                    status="stopped",
                    running_before_shutdown=False,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                model = session.get(Task, task_id)
                if model is None:
                    raise KeyError(task_id)
                if model.status in terminal_statuses:
                    raise RuntimeError(f"cannot stop terminal task in {model.status} state")
                raise RuntimeError(f"cannot stop task in {model.status} state")
            session.commit()
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            return self._record(model)

    def pause_task(self, task_id: str, *, expected_marker: bool) -> TaskRecord:
        """Pause only the unchanged active owner of a task."""
        active_statuses = ("running", "checking", "ordering")
        terminal_statuses = (
            "success",
            "failed",
            "unknown",
            "submitted_pending_confirmation",
        )
        with self.session_factory() as session:
            result = session.execute(
                update(Task)
                .where(
                    Task.id == task_id,
                    Task.status.in_(active_statuses),
                    Task.running_before_shutdown == expected_marker,
                )
                .values(
                    status="paused",
                    running_before_shutdown=False,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                model = session.get(Task, task_id)
                if model is None:
                    raise KeyError(task_id)
                if model.status in terminal_statuses:
                    raise RuntimeError(f"cannot pause terminal task in {model.status} state")
                raise RuntimeError(f"cannot pause task in {model.status} state")
            session.commit()
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            return self._record(model)

    def finalize_submission(
        self,
        task_id: str,
        task_status: str,
        order_status: str,
        observed_price: str | None,
        error: str | None,
    ) -> TaskRecord:
        """Persist task and order outcome as one conditional transaction."""
        active_statuses = ("running", "checking", "ordering")
        indeterminate_status = "submitted_pending_confirmation"
        indeterminate_error = error or "submission outcome is unknown"
        with self.session_factory() as session:
            result = session.execute(
                update(Task)
                .where(Task.id == task_id, Task.status.in_(active_statuses))
                .values(
                    status=task_status,
                    running_before_shutdown=False,
                    last_error=redact_message(error) if error is not None else None,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                model = session.get(Task, task_id)
                if model is None:
                    raise KeyError(task_id)
                if model.status in {"stopped", "paused"}:
                    task_status = indeterminate_status
                    order_status = "unknown"
                    error = indeterminate_error
                    model.status = task_status
                    model.running_before_shutdown = False
                    model.last_error = redact_message(error)
                    model.updated_at = utc_now()
                elif model.status in {
                    "success",
                    "failed",
                    "unknown",
                    indeterminate_status,
                }:
                    return self._record(model)
                else:
                    raise RuntimeError(f"cannot finalize submission from {model.status} state")
            session.add(
                Order(
                    task_id=task_id,
                    status=order_status,
                    observed_price=observed_price,
                    error=redact_message(error) if error is not None else None,
                )
            )
            session.commit()
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            return self._record(model)

    def shutdown_task_lifecycle(
        self,
        task_id: str,
        *,
        expected_marker: bool,
        running_before_shutdown: bool,
    ) -> TaskRecord:
        """Transition only an unchanged active task during manager shutdown."""
        active_statuses = ("running", "checking", "ordering")
        terminal_statuses = (
            "success",
            "failed",
            "unknown",
            "submitted_pending_confirmation",
        )
        with self.session_factory() as session:
            result = session.execute(
                update(Task)
                .where(
                    Task.id == task_id,
                    Task.status.in_(active_statuses),
                    Task.running_before_shutdown == expected_marker,
                )
                .values(
                    status="stopped",
                    running_before_shutdown=running_before_shutdown,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                model = session.get(Task, task_id)
                if model is None:
                    raise KeyError(task_id)
                if model.status in terminal_statuses:
                    session.execute(
                        update(Task)
                        .where(
                            Task.id == task_id,
                            Task.status.in_(terminal_statuses),
                        )
                        .values(running_before_shutdown=False, updated_at=utc_now())
                    )
            session.commit()
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            return self._record(model)

    def recover_active_tasks(self) -> int:
        with self.session_factory() as session:
            models = session.scalars(
                select(Task).where(Task.status.in_(("running", "checking", "ordering")))
            ).all()
            for model in models:
                model.status = "stopped"
                model.running_before_shutdown = False
                model.updated_at = utc_now()
            session.commit()
            return len(models)

    def list_recovery_tasks(self) -> list[TaskRecord]:
        with self.session_factory() as session:
            models = session.scalars(
                select(Task).where(
                    or_(
                        Task.status.in_(("running", "checking", "ordering")),
                        Task.running_before_shutdown.is_(True),
                    ),
                    Task.status.not_in(("success", "failed")),
                )
            ).all()
            return [self._record(model) for model in models]

    def set_task_check_result(self, task_id: str, stock_status: str) -> TaskRecord:
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            model.status = "stopped"
            model.last_stock_status = stock_status
            model.last_checked_at = utc_now()
            model.running_before_shutdown = False
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def set_stock_check_result(self, task_id: str, stock_status: str) -> TaskRecord:
        """Persist poll data without changing task ownership or lifecycle."""
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            model.last_stock_status = stock_status
            model.last_checked_at = utc_now()
            model.updated_at = utc_now()
            session.commit()
            session.refresh(model)
            return self._record(model)

    def create_order(
        self,
        task_id: str,
        status: str,
        observed_price: str | None,
        error: str | None,
    ) -> OrderRecord:
        model = Order(
            task_id=task_id,
            status=status,
            observed_price=observed_price,
            error=redact_message(error) if error is not None else None,
        )
        with self.session_factory() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._order_record(model)

    def list_orders(
        self,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[OrderRecord]:
        safe_limit = max(0, min(limit, 500))
        with self.session_factory() as session:
            query = select(Order).order_by(Order.created_at, Order.id).limit(safe_limit)
            if task_id is not None:
                query = query.where(Order.task_id == task_id)
            if status is not None:
                query = query.where(Order.status == status)
            models = session.scalars(query).all()
            return [self._order_record(model) for model in models]

    def list_task_orders(self, task_id: str) -> list[OrderRecord]:
        with self.session_factory() as session:
            models = session.scalars(
                select(Order)
                .where(Order.task_id == task_id)
                .order_by(Order.created_at, Order.id)
            ).all()
            return [self._order_record(model) for model in models]

    def clear_orders(self) -> None:
        with self.session_factory() as session:
            session.execute(delete(Order))
            session.commit()

    def append_log(self, level: str, task_id: str | None, message: str) -> None:
        with self.session_factory() as session:
            session.add(Log(level=level, task_id=task_id, message=redact_message(message)))
            session.commit()

    def list_logs(
        self, task_id: str | None, level: str | None, limit: int
    ) -> list[LogRecord]:
        safe_limit = max(0, min(limit, 500))
        with self.session_factory() as session:
            query = select(Log).order_by(Log.created_at.desc(), Log.id.desc()).limit(safe_limit)
            if task_id is not None:
                query = query.where(Log.task_id == task_id)
            if level is not None:
                query = query.where(Log.level == level)
            models = session.scalars(query).all()
            return [self._log_record(model) for model in models]

    def clear_logs(self) -> None:
        with self.session_factory() as session:
            session.execute(delete(Log))
            session.commit()

    def get_stats(self) -> dict:
        with self.session_factory() as session:
            task_counts = dict(
                session.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()
            )
            order_counts = dict(
                session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status)).all()
            )
            available_count = session.scalar(
                select(func.count(Task.id)).where(Task.last_stock_status == "available")
            )
            last_error = session.scalar(
                select(Task.last_error)
                .where(Task.last_error.is_not(None))
                .order_by(Task.updated_at.desc())
            )
            return {
                "task_counts": task_counts,
                "order_counts": order_counts,
                "available_count": available_count or 0,
                "last_error": redact_message(last_error) if last_error is not None else None,
            }

    def get_setting(self, key: str) -> str | None:
        with self.session_factory() as session:
            setting = session.get(Setting, key)
            return setting.value_ciphertext if setting else None

    def get_proxy_settings(self) -> dict[str, bool]:
        with self.session_factory() as session:
            setting = session.get(Setting, "__global__")
            return {
                "proxy_enabled": bool(setting and setting.proxy_enabled),
                "proxy_configured": bool(setting and setting.proxy_url_ciphertext),
            }

    def get_global_proxy_settings(self) -> dict[str, bool]:
        return self.get_proxy_settings()

    def update_proxy_settings(
        self,
        *,
        proxy_enabled: bool | None = None,
        proxy_url: str | None | object = _UNSET,
    ) -> None:
        with self.session_factory() as session:
            setting = session.get(Setting, "__global__")
            if setting is None:
                setting = Setting(key="__global__", proxy_enabled=False)
                session.add(setting)
                session.flush()
            if proxy_enabled is not None:
                setting.proxy_enabled = proxy_enabled
                if proxy_enabled is False:
                    setting.proxy_url_ciphertext = None
            if proxy_url is not _UNSET and proxy_enabled is not False:
                if proxy_url is None:
                    setting.proxy_url_ciphertext = None
                else:
                    parse_proxy_url(proxy_url)
                    setting.proxy_url_ciphertext = encrypt_secret(
                        proxy_url, self._encryption_key
                    )
            setting.updated_at = utc_now()
            session.commit()

    def set_global_proxy_settings(
        self, *, proxy_enabled: bool | None = None, proxy_url: str | None | object = _UNSET
    ) -> None:
        self.update_proxy_settings(proxy_enabled=proxy_enabled, proxy_url=proxy_url)

    def get_effective_proxy_url(self, task_id: str) -> str | None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KeyError(task_id)
            if task.proxy_mode == "direct":
                return None
            if task.proxy_mode == "custom":
                if not task.proxy_url_ciphertext:
                    return None
                return decrypt_secret(task.proxy_url_ciphertext, self._encryption_key)
            setting = session.get(Setting, "__global__")
            if not setting or not setting.proxy_enabled or not setting.proxy_url_ciphertext:
                return None
            return decrypt_secret(setting.proxy_url_ciphertext, self._encryption_key)

    def get_global_proxy(self) -> ProxyConfig | None:
        with self.session_factory() as session:
            setting = session.get(Setting, "__global__")
            if not setting or not setting.proxy_enabled or not setting.proxy_url_ciphertext:
                return None
            return parse_proxy_url(
                decrypt_secret(setting.proxy_url_ciphertext, self._encryption_key)
            )

    def get_effective_proxy(self, task_id: str) -> ProxyConfig | None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KeyError(task_id)
            if task.proxy_mode == "direct":
                return None
            if task.proxy_mode == "custom":
                if not task.proxy_url_ciphertext:
                    return None
                return parse_proxy_url(
                    decrypt_secret(task.proxy_url_ciphertext, self._encryption_key)
                )
            setting = session.get(Setting, "__global__")
            if not setting or not setting.proxy_enabled or not setting.proxy_url_ciphertext:
                return None
            return parse_proxy_url(
                decrypt_secret(setting.proxy_url_ciphertext, self._encryption_key)
            )

    def get_task_proxy_url(self, task_id: str) -> str | None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KeyError(task_id)
            if not task.proxy_url_ciphertext:
                return None
            return decrypt_secret(task.proxy_url_ciphertext, self._encryption_key)

    def get_telegram_settings(self) -> dict[str, str | None]:
        """Read Telegram configuration from one database snapshot."""
        keys = ("telegram_enabled", "telegram_bot_token", "telegram_chat_id")
        with self.session_factory() as session:
            values = dict(
                session.execute(
                    select(Setting.key, Setting.value_ciphertext).where(
                        Setting.key.in_(keys)
                    )
                ).all()
            )
        return {key: values.get(key) for key in keys}

    def set_setting(self, key: str, value: str) -> None:
        with self.session_factory() as session:
            setting = session.get(Setting, key)
            if setting is None:
                setting = Setting(key=key, value_ciphertext=value)
                session.add(setting)
            else:
                setting.value_ciphertext = value
                setting.updated_at = utc_now()
            session.commit()

    def set_settings(self, values: dict[str, str]) -> None:
        with self.session_factory() as session:
            now = utc_now()
            for key, value in values.items():
                setting = session.get(Setting, key)
                if setting is None:
                    session.add(
                        Setting(key=key, value_ciphertext=value, updated_at=now)
                    )
                else:
                    setting.value_ciphertext = value
                    setting.updated_at = now
            session.commit()

    def set_settings_atomic(
        self,
        values: dict[str, str],
        *,
        proxy_enabled: bool | object = _UNSET,
        proxy_url_ciphertext: str | None | object = _UNSET,
    ) -> None:
        """Persist all API settings in one transaction."""
        with self.session_factory() as session:
            now = utc_now()
            for key, value in values.items():
                setting = session.get(Setting, key)
                if setting is None:
                    session.add(Setting(key=key, value_ciphertext=value, updated_at=now))
                else:
                    setting.value_ciphertext = value
                    setting.updated_at = now

            if proxy_enabled is not _UNSET or proxy_url_ciphertext is not _UNSET:
                setting = session.get(Setting, "__global__")
                if setting is None:
                    setting = Setting(key="__global__", proxy_enabled=False)
                    session.add(setting)
            if proxy_enabled is not _UNSET:
                setting.proxy_enabled = proxy_enabled
                if proxy_enabled is False:
                    setting.proxy_url_ciphertext = None
            if proxy_url_ciphertext is not _UNSET and proxy_enabled is not False:
                setting.proxy_url_ciphertext = proxy_url_ciphertext
                setting.updated_at = now
            session.commit()

    def get_decrypted_password(self, task_id: str) -> str:
        """Worker-only credential boundary; never use this for API serialization."""
        with self.session_factory() as session:
            model = session.get(Task, task_id)
            if model is None:
                raise KeyError(task_id)
            return decrypt_password(model.password_ciphertext, self._encryption_key)
