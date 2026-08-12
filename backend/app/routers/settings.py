import re
from typing import Literal, Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, validator

from ..security import require_api_key


class SettingsUpdate(BaseModel):
    log_level: Optional[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = Field(default=None, min_length=26, max_length=256)
    telegram_chat_id: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @validator("telegram_bot_token")
    def validate_telegram_bot_token(cls, value):
        if value is not None and not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", value):
            raise ValueError("invalid Telegram bot token format")
        return value

    @validator("telegram_chat_id")
    def validate_telegram_chat_id(cls, value):
        if value is not None and not re.fullmatch(r"-?\d{1,20}", value):
            raise ValueError("Telegram chat ID must be numeric")
        return value

    class Config:
        extra = "forbid"

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_api_key)])


@router.get("")
async def get_settings(request: Request):
    settings = request.app.state.settings
    repository = request.app.state.repository
    return {
        "environment": settings.environment,
        "browser_configured": bool(settings.browser_dsn),
        "api_key_configured": bool(settings.api_key),
        "encryption_key_configured": bool(settings.data_encryption_key),
        "telegram_enabled": repository.get_setting("telegram_enabled") == "true",
        "telegram_configured": bool(request.app.state.telegram_notifier.is_configured()),
        "log_level": (
            repository.get_setting("log_level") or settings.log_level
        ).upper(),
    }


@router.put("")
async def update_settings(payload: SettingsUpdate, request: Request):
    repository = request.app.state.repository
    values = payload.dict(exclude_unset=True)
    encrypted = {}
    cipher = Fernet(request.app.state.settings.data_encryption_key.encode("ascii"))
    for key, value in values.items():
        if key in {"telegram_bot_token", "telegram_chat_id"}:
            encrypted[key] = cipher.encrypt(str(value).encode("utf-8")).decode("ascii")
        else:
            encrypted[key] = str(value).lower() if isinstance(value, bool) else str(value)
    repository.set_settings(encrypted)
    return await get_settings(request)


telegram_router = APIRouter(prefix="/api/telegram", dependencies=[Depends(require_api_key)])


@telegram_router.post("/test")
async def test_telegram(request: Request):
    try:
        success = await request.app.state.telegram_notifier.test()
    except Exception:
        success = False
    return {
        "success": bool(success),
        "message": (
            "Telegram test notification sent"
            if success
            else "Telegram test notification failed"
        ),
    }
