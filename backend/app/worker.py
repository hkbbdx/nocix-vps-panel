from __future__ import annotations

import logging
import inspect
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunsplit

from nocix_fucker.types import PaymentMethod

from .redaction import redact_message


ClientFactory = Callable[[], Any]
Repository = Any
LogCallback = Callable[..., None]
NotifierCallback = Callable[[str], None]


@dataclass
class VerificationState:
    """Private, thread-safe coordination state for one login session."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    event: threading.Event = field(default_factory=threading.Event)
    pending_code: str | None = None
    deadline: float = 0.0
    attempts: int = 0
    last_error: str | None = None
    status: str = "stopped"
    cancelled: bool = False
    attempt_in_flight: bool = False

    def begin(self, deadline: float) -> None:
        with self.lock:
            self.deadline = deadline
            self.pending_code = None
            self.attempt_in_flight = False
            self.cancelled = False
            self.last_error = None
            self.event.clear()

    def submit(self, code: str, now: float) -> bool:
        with self.lock:
            if self.cancelled or self.pending_code is not None:
                return False
            if self.attempt_in_flight:
                return False
            if now >= self.deadline:
                self.pending_code = None
                self.event.set()
                return False
            self.pending_code = code
            self.event.set()
            return True

    def consume(self, now: float) -> tuple[str | None, str | None]:
        with self.lock:
            code = self.pending_code
            if code is not None and now >= self.deadline:
                self.pending_code = None
                self.event.clear()
                return "timeout", None
            self.pending_code = None
            cancelled = self.cancelled
            self.event.clear()
            if code is not None:
                self.attempts += 1
                self.attempt_in_flight = True
                return "code", code
            return ("cancel", None) if cancelled else (None, None)

    def finalize_attempt(
        self,
        accepted: bool,
        now: float,
        stop_event: threading.Event,
        pause_event: threading.Event,
    ) -> str:
        with self.lock:
            self.pending_code = None
            self.attempt_in_flight = False
            if self.cancelled:
                return "cancelled"
            if stop_event.is_set() or pause_event.is_set():
                return "interrupted"
            if now >= self.deadline:
                return "timeout"
            return "accepted" if accepted else "rejected"

    def cancel(self, message: str) -> bool:
        with self.lock:
            self.cancelled = True
            self.pending_code = None
            self.last_error = message
            self.event.set()
            return True

    def wake(self) -> None:
        with self.lock:
            self.event.set()

    def set_error(self, message: str | None) -> None:
        with self.lock:
            self.last_error = message

    def public(self, task_id: str, status: str, clock: Callable[[], float]) -> dict:
        with self.lock:
            remaining = max(0.0, self.deadline - clock()) if self.deadline else 0.0
            return {
                "task_id": task_id,
                "status": status,
                "waiting": status == "waiting_for_email_code" and not self.cancelled,
                "attempts": self.attempts,
                "remaining_seconds": int(remaining + 0.999) if remaining else 0,
                "last_error": self.last_error,
            }

    def cleanup(self) -> None:
        with self.lock:
            self.pending_code = None
            self.attempt_in_flight = False
            self.deadline = 0.0
            self.attempts = 0
            self.last_error = None
            self.cancelled = True
            self.event.clear()


class CheckoutWorker:
    """Run one isolated, terminal NOCIX checkout attempt."""

    def __init__(
        self,
        task: Any,
        *,
        client_factory: ClientFactory,
        repository: Repository,
        logger: LogCallback | None = None,
        notifier: NotifierCallback | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        stop_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        verification_timeout: float = 300.0,
    ) -> None:
        self.task = task
        self.client_factory = client_factory
        self.repository = repository
        if logger is None:
            self.logger = lambda level, message: logging.getLogger(__name__).log(
                getattr(logging, level, logging.INFO), message
            )
        else:
            self.logger = logger
        self.notifier = notifier or (lambda message: None)
        self.sleep = sleep
        self.clock = clock
        self.verification_timeout = max(0.0, float(verification_timeout))
        self.stop_event = stop_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self._run_lock = threading.Lock()
        self._terminal = False
        self._persistence_blocked = False
        self._stock_was_unavailable = False
        self._last_stock_status: str | None = None
        self._submit_called = False
        self._phase = "checking"
        self._order_attempt_started = False
        self._verification = VerificationState(status="stopped")
        self._logger_accepts_level = logger is None or self._callback_accepts_level(logger)

    def _value(self, name: str, default: Any = None) -> Any:
        if isinstance(self.task, dict):
            return self.task.get(name, default)
        return getattr(self.task, name, default)

    def _task_id(self) -> str:
        return str(self._value("id", "unknown"))

    def _product_id(self) -> str:
        return str(self._value("goods_id", "unknown"))

    @staticmethod
    def _callback_accepts_level(callback: LogCallback | None) -> bool:
        if callback is None:
            return False
        try:
            parameters = inspect.signature(callback).parameters.values()
        except (TypeError, ValueError):
            return True
        parameters = list(parameters)
        return any(
            parameter.kind is parameter.VAR_POSITIONAL
            or parameter.kind is parameter.KEYWORD_ONLY
            or parameter.kind is parameter.POSITIONAL_OR_KEYWORD
            for parameter in parameters[1:]
        )

    def _log(self, message: str, level: str = "INFO") -> None:
        safe_message = redact_message(message)
        try:
            if self._logger_accepts_level:
                self.logger(level, safe_message)
            else:
                self.logger(safe_message)
        except Exception as exc:
            self._callback_warning("logger", exc)

    def _notify(self, message: str) -> None:
        safe_message = redact_message(message)
        try:
            if hasattr(self.notifier, "send_sync"):
                self.notifier.send_sync(
                    {
                        "task_id": self._task_id(),
                        "product_id": self._product_id(),
                        "message": safe_message,
                    }
                )
            else:
                self.notifier(safe_message)
        except Exception as exc:
            self._callback_warning("notifier", exc)

    def _set_status(self, status: str, error: str | None = None) -> None:
        with self._verification.lock:
            self._verification.status = status
        try:
            self.repository.set_task_status(self._task_id(), status, error=error)
        except Exception as exc:
            self._callback_warning("repository status", exc)

    def _order(self, status: str, error: str | None = None) -> None:
        try:
            self.repository.create_order(
                self._task_id(), status, observed_price=self._observed_price(), error=error
            )
        except Exception as exc:
            self._callback_warning("repository order", exc)

    def _finalize_submission(
        self,
        task_status: str,
        order_status: str,
        error: str | None = None,
    ) -> str | None:
        finalize = getattr(self.repository, "finalize_submission", None)
        if callable(finalize):
            attempts = [(task_status, order_status, error)]
            if task_status != "submitted_pending_confirmation":
                attempts.append(
                    (
                        "submitted_pending_confirmation",
                        "unknown",
                        error or "submission outcome is unknown",
                    )
                )
            for attempt_status, attempt_order, attempt_error in attempts:
                try:
                    record = finalize(
                        self._task_id(),
                        attempt_status,
                        attempt_order,
                        observed_price=self._observed_price(),
                        error=attempt_error,
                    )
                    persisted_status = getattr(record, "status", None)
                    if persisted_status in {
                        attempt_status,
                        "unknown",
                        "submitted_pending_confirmation",
                    }:
                        return persisted_status
                    self._callback_warning(
                        "repository submission finalization",
                        RuntimeError("repository returned no terminal submission record"),
                    )
                except Exception as exc:
                    self._callback_warning("repository submission finalization", exc)
            try:
                self.repository.set_task_status(
                    self._task_id(),
                    "submitted_pending_confirmation",
                    error=error or "submission outcome is unknown",
                )
                self.repository.create_order(
                    self._task_id(),
                    "unknown",
                    observed_price=self._observed_price(),
                    error=error or "submission outcome is unknown",
                )
                return "submitted_pending_confirmation"
            except Exception as exc:
                self._callback_warning("repository indeterminate submission fallback", exc)
            self._persistence_blocked = True
            return None
        try:
            self.repository.set_task_status(self._task_id(), task_status, error=error)
            self.repository.create_order(
                self._task_id(), order_status, observed_price=self._observed_price(), error=error
            )
            return task_status
        except Exception as exc:
            self._callback_warning("repository submission finalization fallback", exc)
            self._persistence_blocked = True
            try:
                self.repository.set_task_status(
                    self._task_id(),
                    "submitted_pending_confirmation",
                    error=error or "submission outcome is unknown",
                )
            except Exception as unknown_exc:
                self._callback_warning("repository indeterminate status fallback", unknown_exc)
            return None

    @staticmethod
    def _callback_warning(kind: str, exc: Exception) -> None:
        logging.getLogger(__name__).warning(
            "Worker %s callback failed: %s", kind, redact_message(exc)
        )

    def _observed_price(self) -> str | None:
        value = getattr(self, "_client", None)
        return getattr(value, "last_price_text", None) if value is not None else None

    @staticmethod
    def _call_with_url(method: Callable[..., Any], goods_id: str, url: str | None) -> Any:
        if url:
            try:
                parameters = inspect.signature(method).parameters.values()
                accepts_url = any(
                    parameter.kind is parameter.VAR_POSITIONAL
                    or parameter.kind in {
                        parameter.POSITIONAL_ONLY,
                        parameter.POSITIONAL_OR_KEYWORD,
                    }
                    for parameter in list(parameters)[1:]
                )
            except (TypeError, ValueError):
                accepts_url = True
            if accepts_url:
                return method(goods_id, url)
        return method(goods_id)

    def _interrupt_requested(self) -> bool:
        if self.stop_event.is_set():
            self._verification.wake()
            self._terminal = True
            self._set_status("stopped")
            return True
        if self.pause_event.is_set():
            self._verification.wake()
            self._set_status("paused")
            return True
        return False

    def get_login_state(self) -> dict:
        with self._verification.lock:
            status = self._verification.status
        return self._verification.public(self._task_id(), status, self.clock)

    def submit_email_code(self, code: str) -> dict:
        with self._verification.lock:
            in_flight = self._verification.attempt_in_flight
            waiting = self._verification.status == "waiting_for_email_code"
        if in_flight:
            state = self.get_login_state()
            return {
                "accepted": False,
                "status": state["status"],
                "message": "verification attempt already in flight",
            }
        if not isinstance(code, str) or re.fullmatch(r"[0-9]{4,12}", code) is None:
            state = self.get_login_state()
            return {
                "accepted": False,
                "status": state["status"],
                "message": "invalid verification code",
            }
        if not waiting or not self._verification.submit(code, self.clock()):
            state = self.get_login_state()
            return {
                "accepted": False,
                "status": state["status"],
                "message": "login verification is not accepting a code",
            }
        state = self.get_login_state()
        return {"accepted": True, "status": state["status"], "message": "code submitted"}

    def cancel_verification(self, message: str = "verification cancelled") -> bool:
        with self._verification.lock:
            waiting = self._verification.status == "waiting_for_email_code"
        return waiting and self._verification.cancel(message)

    def wake_verification(self) -> None:
        self._verification.wake()

    def _wait_for_email_code(self, client: Any) -> bool:
        self._verification.begin(self.clock() + self.verification_timeout)
        self._set_status("waiting_for_email_code")
        while True:
            if self._interrupt_requested():
                return False
            with self._verification.lock:
                remaining = max(0.0, self._verification.deadline - self.clock())
            if remaining <= 0:
                self._verification.set_error("email verification failed")
                self._fail("email verification failed")
                return False
            self._verification.event.wait(timeout=remaining)
            if self._interrupt_requested():
                return False
            action, code = self._verification.consume(self.clock())
            if action == "cancel":
                self._fail("verification cancelled", level="WARNING")
                return False
            if action == "timeout":
                self._fail("email verification failed")
                return False
            if action != "code" or code is None:
                continue
            try:
                accepted = bool(client.submit_email_code(code))
            except Exception:
                outcome = self._verification.finalize_attempt(
                    False, self.clock(), self.stop_event, self.pause_event
                )
                if outcome == "cancelled":
                    self._fail("verification cancelled", level="WARNING")
                elif outcome == "interrupted":
                    self._interrupt_requested()
                elif outcome == "timeout":
                    self._fail("email verification failed")
                else:
                    self._fail("email verification failed")
                return False
            outcome = self._verification.finalize_attempt(
                accepted, self.clock(), self.stop_event, self.pause_event
            )
            if outcome == "cancelled":
                self._fail("verification cancelled", level="WARNING")
                return False
            if outcome == "interrupted":
                self._interrupt_requested()
                return False
            if outcome == "timeout":
                self._fail("email verification failed")
                return False
            if outcome == "accepted":
                self._verification.set_error(None)
                return True
            self._verification.set_error("email verification failed")
            self._set_status("waiting_for_email_code", "email verification failed")

    def _wait(self, seconds: float) -> bool:
        # The adapter deliberately wakes at most once per second so lifecycle
        # events can interrupt a long stock interval.
        deadline = self.clock() + max(0.0, seconds)
        while self.clock() < deadline:
            if self._interrupt_requested():
                return False
            remaining = min(1.0, max(0.0, deadline - self.clock()))
            self.sleep(remaining)
        return not self._interrupt_requested()

    def _paypal_redirect(self, client: Any) -> str | None:
        url = str(getattr(client, "current_url", "") or "")
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if hostname == "paypal.com" or hostname.endswith(".paypal.com"):
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        if hostname == "paypalobjects.com" or hostname.endswith(".paypalobjects.com"):
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        return None

    def _fail(self, message: str, *, level: str = "ERROR") -> None:
        safe_message = redact_message(message)
        self._terminal = True
        self._set_status("failed", safe_message)
        if self._order_attempt_started:
            self._order("failed", safe_message)
        self._log(safe_message, level)
        self._notify(f"Task {self._task_id()} failed: {safe_message}")

    def _submit_failed(self, message: str) -> None:
        safe_message = redact_message(message)
        final_status = self._finalize_submission("failed", "failed", safe_message)
        self._terminal = True
        if final_status is None:
            self._submission_persistence_failed(safe_message)
            return
        if final_status in {"unknown", "submitted_pending_confirmation"}:
            self._log(f"submission outcome unknown: {safe_message}", "ERROR")
            self._notify(
                f"Task {self._task_id()} submission outcome unknown: {safe_message}"
            )
            return
        self._log(safe_message, "ERROR")
        self._notify(f"Task {self._task_id()} failed: {safe_message}")

    def _interrupt_after_submit(self, status: str) -> None:
        message = f"interrupted after submit: {status}"
        safe_message = redact_message(message)
        self._terminal = True
        if self._finalize_submission("submitted_pending_confirmation", "unknown", safe_message) is None:
            self._submission_persistence_failed(safe_message)
            return
        self._log(safe_message, "ERROR")
        self._notify(f"Task {self._task_id()} submission outcome unknown: {safe_message}")

    def _unknown_after_submit(self, message: str) -> None:
        safe_message = redact_message(message)
        self._terminal = True
        if self._finalize_submission("submitted_pending_confirmation", "unknown", safe_message) is None:
            self._submission_persistence_failed(safe_message)
            return
        self._log(safe_message, "ERROR")
        self._notify(f"Task {self._task_id()} submission outcome unknown: {safe_message}")

    def _submission_persistence_failed(self, message: str) -> None:
        self._persistence_blocked = True
        safe_message = redact_message(
            f"submission outcome could not be persisted; task ownership retained: {message}"
        )
        self._log(safe_message, "ERROR")
        self._notify(f"Task {self._task_id()} submission persistence failure: {safe_message}")

    def run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            return
        client = None
        try:
            if self._terminal:
                return
            if self._interrupt_requested():
                return
            self._log(
                f"Task {self._task_id()} product {self._product_id()} "
                "checkout worker started"
            )
            if self._value("auto_submit", True) is not True:
                self._fail("auto_submit must be true")
                return
            self._client = client = self.client_factory()
            self._set_status("checking")
            while True:
                if self._interrupt_requested():
                    return
                stock_url = self._value("stock_url")
                available = self._call_with_url(
                    client.check_stock, self._value("goods_id"), stock_url
                )
                stock_status = "available" if available else "out_of_stock"
                try:
                    set_stock_result = getattr(
                        self.repository, "set_stock_check_result", None
                    )
                    if callable(set_stock_result):
                        set_stock_result(self._task_id(), stock_status)
                    else:
                        self.repository.set_task_check_result(
                            self._task_id(), stock_status
                        )
                except Exception as exc:
                    self._log(
                        f"stock check result could not be persisted: {exc}",
                        "WARNING",
                    )
                if self._last_stock_status != stock_status:
                    if stock_status == "available":
                        message = (
                            f"Task {self._task_id()} product {self._product_id()} "
                            "stock available; checkout starting"
                        )
                    else:
                        message = (
                            f"Task {self._task_id()} product {self._product_id()} "
                            "stock out_of_stock"
                        )
                    self._log(message)
                    self._last_stock_status = stock_status
                if available:
                    if self._stock_was_unavailable:
                        self._notify(
                            f"Task {self._task_id()} product {self._product_id()} "
                            "stock recovered; checkout starting"
                        )
                    break
                self._stock_was_unavailable = True
                if not self._wait(float(self._value("wait_interval", 5.0))):
                    return
                if self._interrupt_requested():
                    return

            if self._interrupt_requested():
                return
            self._phase = "ordering"
            self._set_status("ordering")
            cart_url = self._value("cart_url")
            self._call_with_url(client.open_cart, self._value("goods_id"), cart_url)
            if self._interrupt_requested():
                return

            login = getattr(client, "login_existing_customer", None)
            if callable(login):
                password = self.repository.get_decrypted_password(self._task_id())
                self._phase = "login_first"
                self._set_status("login_first")
                try:
                    login_ok = bool(login(self._value("email"), password))
                except Exception:
                    self._fail("login failed", level="WARNING")
                    return
                self._phase = "login_second"
                self._set_status("login_second")
                try:
                    code_required = bool(client.is_email_code_required())
                except Exception:
                    self._fail("email verification failed")
                    return
                if not login_ok and not code_required:
                    self._fail("login failed", level="WARNING")
                    return
                if code_required and not self._wait_for_email_code(client):
                    return
                self._set_status("ordering")

            redirect = self._paypal_redirect(client)
            if redirect:
                self._fail(f"PayPal redirect blocked at url={redirect}")
                return

            operating_system = str(self._value("operating_system", "debian"))
            if self._interrupt_requested():
                return
            if not client.select_operating_system(operating_system):
                if self._interrupt_requested():
                    return
                if operating_system != "debian" or not client.select_operating_system("ubuntu"):
                    self._fail("configured operating system is unavailable", level="WARNING")
                    return
            if self._interrupt_requested():
                return
            if self._interrupt_requested():
                return
            if not client.match_price(float(self._value("target_price"))):
                self._fail("price mismatch", level="WARNING")
                return
            if self._interrupt_requested():
                return

            if self._interrupt_requested():
                return
            password = self.repository.get_decrypted_password(self._task_id())
            if self._interrupt_requested():
                return
            client.fill_in_customer_info(
                new=False,
                email=self._value("email"),
                password=password,
            )
            self._order_attempt_started = True
            if self._interrupt_requested():
                return
            if self._interrupt_requested():
                return
            client.fill_in_payment_info(payment_method=PaymentMethod.PAYPAL)
            if self._interrupt_requested():
                return
            if self._block_paypal_redirect(client):
                return
            if self._interrupt_requested():
                return
            client.click_next_step_button()
            if self._interrupt_requested():
                return
            if self._block_paypal_redirect(client):
                return
            if self._interrupt_requested():
                return
            self._submit_called = True
            self._phase = "submitted"
            result = client.submit_order()
            if self._block_paypal_redirect(client):
                return
            if self.stop_event.is_set():
                self._interrupt_after_submit("stopped")
                return
            if self.pause_event.is_set():
                self._interrupt_after_submit("paused")
                return
            if result:
                self._submit_failed(str(result))
                return

            final_status = self._finalize_submission("success", "success")
            self._terminal = True
            if final_status is None:
                self._submission_persistence_failed("submission outcome is unknown")
                return
            if final_status in {"submitted_pending_confirmation", "unknown"}:
                message = "submission outcome unknown after finalization"
                self._log(message, "ERROR")
                self._notify(f"Task {self._task_id()} submission outcome unknown: {message}")
                return
            self._log(f"Task {self._task_id()} order submitted", "INFO")
            self._notify(f"Task {self._task_id()} order submitted")
        except Exception as exc:
            if self._submit_called:
                self._unknown_after_submit(str(exc))
            else:
                self._fail(str(exc))
        finally:
            self._verification.cleanup()
            if client is not None:
                try:
                    client.close()
                except Exception as exc:
                    self._callback_warning("client cleanup", exc)
            self._run_lock.release()

    def _block_paypal_redirect(self, client: Any) -> bool:
        redirect = self._paypal_redirect(client)
        if redirect is None:
            return False
        if getattr(self, "_submit_called", False):
            self._unknown_after_submit(f"PayPal redirect blocked at url={redirect}")
        else:
            self._fail(f"PayPal redirect blocked at url={redirect}")
        return True
