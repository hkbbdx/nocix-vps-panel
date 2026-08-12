from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .redaction import redact_message


class TelegramNotifier:
    """Best-effort Telegram Bot API notifier backed by encrypted settings."""

    _TOKEN_KEY = "telegram_bot_token"
    _CHAT_ID_KEY = "telegram_chat_id"
    _ENABLED_KEY = "telegram_enabled"

    def __init__(
        self,
        repository: Any,
        settings: Any,
        *,
        client_factory: Callable[..., Any] = httpx.AsyncClient,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.client_factory = client_factory
        self.logger = logger or logging.getLogger(__name__).warning

    def _cipher(self) -> Fernet | None:
        key = getattr(self.settings, "data_encryption_key", None)
        if not key:
            return None
        try:
            return Fernet(key.encode("ascii"))
        except (AttributeError, UnicodeEncodeError, ValueError):
            return None

    def _decrypted_setting(self, ciphertext: str | None) -> str | None:
        cipher = self._cipher()
        if not ciphertext or cipher is None:
            return None
        try:
            return cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (UnicodeEncodeError, InvalidToken, ValueError):
            return None

    def _credentials(self, snapshot: dict[str, str | None]) -> tuple[str, str] | None:
        token = self._decrypted_setting(snapshot.get(self._TOKEN_KEY))
        chat_id = self._decrypted_setting(snapshot.get(self._CHAT_ID_KEY))
        if not token or not chat_id:
            return None
        return token, chat_id

    def is_configured(self) -> bool:
        try:
            return self._credentials(self.repository.get_telegram_settings()) is not None
        except Exception as exc:
            self._warning(
                "Telegram configuration lookup failed: "
                f"{redact_message(type(exc).__name__)}"
            )
            return False

    @staticmethod
    def _message_text(event: Any) -> str:
        if isinstance(event, dict):
            task_id = event.get("task_id", "unknown")
            product_id = event.get("product_id", "unknown")
            message = event.get("message", "")
            return redact_message(
                f"Task {task_id} product {product_id}: {message}"
            )
        return redact_message(event)

    def _warning(
        self,
        message: Any,
        *,
        task_id: str | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        safe_message = redact_message(message)
        for secret in secrets:
            if secret:
                safe_message = safe_message.replace(secret, "***REDACTED***")
        try:
            append_log = getattr(self.repository, "append_log", None)
            if append_log is not None:
                try:
                    append_log("WARNING", task_id, safe_message)
                except Exception:
                    try:
                        append_log("WARNING", None, safe_message)
                    except Exception:
                        pass
            try:
                self.logger(safe_message)
            except Exception:
                pass
        except Exception:
            pass

    async def _send(self, event: Any, *, require_enabled: bool) -> bool:
        try:
            snapshot = self.repository.get_telegram_settings()
            credentials = self._credentials(snapshot)
            if credentials is None:
                if snapshot.get(self._TOKEN_KEY) or snapshot.get(self._CHAT_ID_KEY):
                    self._warning(
                        "Telegram credentials are unavailable",
                        task_id=self._event_task_id(event),
                    )
                return False
            if require_enabled and snapshot.get(self._ENABLED_KEY) != "true":
                return False
        except Exception as exc:
            self._warning(
                "Telegram configuration lookup failed: "
                f"{redact_message(type(exc).__name__)}",
                task_id=self._event_task_id(event),
            )
            return False

        token, chat_id = credentials
        text = self._message_text(event)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with self.client_factory(timeout=10.0) as client:
                response = await client.post(
                    url,
                    data={"chat_id": chat_id, "text": text},
                )
            if not 200 <= response.status_code < 300:
                self._warning(
                    f"Telegram request failed with HTTP status {response.status_code}",
                    task_id=self._event_task_id(event),
                    secrets=(token, chat_id),
                )
                return False
            try:
                payload = response.json()
            except (TypeError, ValueError):
                self._warning(
                    "Telegram returned malformed JSON",
                    task_id=self._event_task_id(event),
                    secrets=(token, chat_id),
                )
                return False
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                self._warning(
                    "Telegram API returned ok=false",
                    task_id=self._event_task_id(event),
                    secrets=(token, chat_id),
                )
                return False
            return True
        except Exception as exc:
            safe_error = redact_message(exc).replace(token, "***REDACTED***").replace(
                chat_id, "***REDACTED***"
            )
            self._warning(
                f"Telegram notification failed: {safe_error}",
                task_id=self._event_task_id(event),
                secrets=(token, chat_id),
            )
            return False

    @staticmethod
    def _event_task_id(event: Any) -> str | None:
        if isinstance(event, dict):
            value = event.get("task_id")
            return str(value) if value is not None else None
        return None

    async def send(self, event: Any) -> bool:
        return await self._send(event, require_enabled=True)

    async def test(self) -> bool:
        return await self._send("NOCIX Telegram test notification", require_enabled=False)

    def send_sync(self, event: Any) -> bool:
        return asyncio.run(self.send(event))
