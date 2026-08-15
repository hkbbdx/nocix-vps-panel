from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Request

from ..security import require_api_key
from ..schemas import SettingsUpdate

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
        **repository.get_proxy_settings(),
    }


@router.put("")
async def update_settings(payload: SettingsUpdate, request: Request):
    repository = request.app.state.repository
    values = payload.dict(exclude_unset=True)
    encrypted = {}
    cipher = Fernet(request.app.state.settings.data_encryption_key.encode("ascii"))
    proxy_kwargs = {}
    if "proxy_enabled" in values:
        proxy_kwargs["proxy_enabled"] = values.pop("proxy_enabled")
    if "proxy_url" in values:
        proxy_url = values.pop("proxy_url")
        proxy_url_ciphertext = (
            cipher.encrypt(proxy_url.encode("utf-8")).decode("ascii")
            if proxy_url is not None
            else None
        )
        proxy_kwargs["proxy_url_ciphertext"] = proxy_url_ciphertext
    for key, value in values.items():
        if key in {"telegram_bot_token", "telegram_chat_id"}:
            encrypted[key] = cipher.encrypt(str(value).encode("utf-8")).decode("ascii")
        else:
            encrypted[key] = str(value).lower() if isinstance(value, bool) else str(value)
    repository.set_settings_atomic(encrypted, **proxy_kwargs)
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
