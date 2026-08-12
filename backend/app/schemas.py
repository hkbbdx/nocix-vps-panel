import math
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, root_validator, validator


def _validate_http_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    parsed = urlparse(value)
    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        hostname = None
    hostname = hostname.lower().rstrip(".") if hostname else None
    allowed_host = hostname == "nocix.net" or (
        hostname is not None and hostname.endswith(".nocix.net")
    )
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or not allowed_host
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() for character in value)
    ):
        raise ValueError("URL must use http or https")
    return value


def _validate_finite(value: Optional[float]) -> Optional[float]:
    if value is not None and not math.isfinite(value):
        raise ValueError("value must be finite")
    return value


class _TaskConstraints(BaseModel):
    new_customer: Literal[False] = False
    payment_method: Literal["paypal"] = "paypal"

    class Config:
        extra = "forbid"


class TaskCreate(_TaskConstraints):
    goods_id: str = Field(..., min_length=1, regex=r"^[0-9]+$")
    stock_url: Optional[str] = None
    cart_url: Optional[str] = None
    target_price: float = Field(..., gt=0)
    wait_interval: float = Field(default=5, ge=2)
    operating_system: Literal["debian", "ubuntu"] = "debian"
    email: EmailStr
    password: str = Field(..., min_length=1)
    auto_submit: Literal[True] = True

    _stock_url_is_http = validator("stock_url", allow_reuse=True)(_validate_http_url)
    _cart_url_is_http = validator("cart_url", allow_reuse=True)(_validate_http_url)
    _target_price_is_finite = validator("target_price", allow_reuse=True)(
        _validate_finite
    )
    _wait_interval_is_finite = validator("wait_interval", allow_reuse=True)(
        _validate_finite
    )

    @root_validator
    def apply_url_defaults(cls, values):
        goods_id = values.get("goods_id")
        if goods_id:
            if not values.get("stock_url"):
                values["stock_url"] = (
                    f"https://nocix.net/out-of-stock/?id={goods_id}"
                )
            if not values.get("cart_url"):
                values["cart_url"] = f"https://nocix.net/cart/?id={goods_id}"
        return values


class TaskUpdate(_TaskConstraints):
    goods_id: Optional[str] = Field(default=None, min_length=1, regex=r"^[0-9]+$")
    stock_url: Optional[str] = None
    cart_url: Optional[str] = None
    target_price: Optional[float] = Field(default=None, gt=0)
    wait_interval: Optional[float] = Field(default=None, ge=2)
    operating_system: Optional[Literal["debian", "ubuntu"]] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=1)
    auto_submit: Optional[Literal[True]] = None

    _stock_url_is_http = validator("stock_url", allow_reuse=True)(_validate_http_url)
    _cart_url_is_http = validator("cart_url", allow_reuse=True)(_validate_http_url)
    _target_price_is_finite = validator("target_price", allow_reuse=True)(
        _validate_finite
    )
    _wait_interval_is_finite = validator("wait_interval", allow_reuse=True)(
        _validate_finite
    )

    @validator("stock_url", "cart_url", pre=True)
    def reject_null_urls(cls, value):
        if value is None:
            raise ValueError("URL cannot be null when updating a task")
        return value


class TaskResponse(BaseModel):
    id: str
    goods_id: str
    stock_url: str
    cart_url: str
    target_price: float = Field(..., gt=0)
    wait_interval: float = Field(..., ge=2)
    operating_system: Literal["debian", "ubuntu"]
    email: EmailStr
    new_customer: Literal[False] = False
    payment_method: Literal["paypal"] = "paypal"
    auto_submit: Literal[True] = True
    password_configured: bool
    status: str = "stopped"
    last_stock_status: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None

    _target_price_is_finite = validator("target_price", allow_reuse=True)(
        _validate_finite
    )
    _wait_interval_is_finite = validator("wait_interval", allow_reuse=True)(
        _validate_finite
    )

    class Config:
        extra = "forbid"


class SettingsUpdate(BaseModel):
    log_level: Optional[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = None
    telegram_enabled: Optional[bool] = None

    class Config:
        extra = "forbid"
