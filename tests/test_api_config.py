import asyncio

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.schemas import TaskCreate, TaskResponse, TaskUpdate
from backend.app.config import get_settings
from backend.app.security import require_api_key


def task_data(**overrides):
    data = {
        "goods_id": "418",
        "target_price": 59,
        "wait_interval": 5,
        "email": "buyer@example.com",
        "password": "secret",
    }
    data.update(overrides)
    return data


def test_task_accepts_existing_paypal_account():
    task = TaskCreate(**task_data())

    assert task.payment_method == "paypal"
    assert task.new_customer is False
    assert task.operating_system == "debian"
    assert task.auto_submit is True


def test_task_rejects_auto_submit_false():
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(auto_submit=False))
    with pytest.raises(ValidationError):
        TaskUpdate(auto_submit=False)


@pytest.mark.parametrize("field", ["email", "password"])
def test_task_requires_existing_account_credentials(field):
    data = task_data()
    del data[field]

    with pytest.raises(ValidationError):
        TaskCreate(**data)


def test_task_rejects_generic_unknown_field():
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(unexpected="value"))


@pytest.mark.parametrize("field", ["cc_num", "cc_ccv", "CC_NUM"])
def test_task_rejects_card_fields(field):
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(**{field: "4111111111111111"}))


def test_task_rejects_new_customer():
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(new_customer=True))


def test_task_rejects_non_paypal_payment():
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(payment_method="bitcoin"))


@pytest.mark.parametrize("field, value", [("target_price", 0), ("wait_interval", 1)])
def test_task_rejects_bad_price_or_interval(field, value):
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(**{field: value}))


def test_task_uses_goods_id_url_defaults():
    task = TaskCreate(**task_data())

    assert task.stock_url == "https://nocix.net/out-of-stock/?id=418"
    assert task.cart_url == "https://nocix.net/cart/?id=418"


def test_task_validates_explicit_http_urls():
    task = TaskCreate(
        **task_data(
            stock_url="http://nocix.net/stock",
            cart_url="https://nocix.net/cart",
        )
    )

    assert task.stock_url == "http://nocix.net/stock"
    assert task.cart_url == "https://nocix.net/cart"


def test_task_accepts_nocix_subdomain_urls():
    task = TaskCreate(
        **task_data(
            stock_url="https://shop.nocix.net/stock",
            cart_url="http://checkout.nocix.net/cart",
        )
    )

    assert task.stock_url == "https://shop.nocix.net/stock"
    assert task.cart_url == "http://checkout.nocix.net/cart"


@pytest.mark.parametrize(
    "field, value",
    [
        ("stock_url", "ftp://nocix.net/item"),
        ("cart_url", "file:///tmp/cart"),
        ("stock_url", "http://"),
        ("cart_url", "https://"),
        ("stock_url", "http://not a valid host"),
        ("stock_url", "https://example.com/stock"),
        ("cart_url", "https://localhost/cart"),
        ("stock_url", "https://127.0.0.1/stock"),
        ("cart_url", "https://169.254.169.254/latest/meta-data"),
        ("stock_url", "https://evilnocix.net/stock"),
        ("cart_url", "https://nocix.net.evil.example/cart"),
        ("stock_url", "https://user:pass@nocix.net/stock"),
    ],
)
def test_task_rejects_invalid_or_malformed_urls(field, value):
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(**{field: value}))


def test_task_rejects_goods_id_injection():
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(goods_id="418&redirect=https://evil.example"))


def test_task_update_allows_editable_fields_and_optional_password():
    update = TaskUpdate(
        target_price=70,
        wait_interval=10,
        operating_system="ubuntu",
        password="replacement",
    )

    assert update.target_price == 70
    assert update.password == "replacement"


def test_task_update_keeps_paypal_existing_account_constraints():
    with pytest.raises(ValidationError):
        TaskUpdate(new_customer=True)
    with pytest.raises(ValidationError):
        TaskUpdate(payment_method="credit_card")


@pytest.mark.parametrize("field", ["unexpected", "cc_num", "CC_NUM"])
def test_task_update_rejects_unknown_or_card_fields(field):
    with pytest.raises(ValidationError):
        TaskUpdate(**{field: "value"})


def test_task_update_rejects_empty_password():
    with pytest.raises(ValidationError):
        TaskUpdate(password="")


@pytest.mark.parametrize(
    "field, value",
    [
        ("target_price", 0),
        ("target_price", -1),
        ("wait_interval", 1),
        ("wait_interval", 0),
        ("operating_system", "windows"),
    ],
)
def test_task_update_rejects_invalid_editable_values(field, value):
    with pytest.raises(ValidationError):
        TaskUpdate(**{field: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_task_create_rejects_non_finite_numbers(value):
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(target_price=value))
    with pytest.raises(ValidationError):
        TaskCreate(**task_data(wait_interval=value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_task_update_rejects_non_finite_numbers(value):
    with pytest.raises(ValidationError):
        TaskUpdate(target_price=value)
    with pytest.raises(ValidationError):
        TaskUpdate(wait_interval=value)


def test_task_response_does_not_expose_plaintext_password():
    response = TaskResponse(
        id="task-1",
        goods_id="418",
        stock_url="https://nocix.net/out-of-stock/?id=418",
        cart_url="https://nocix.net/cart/?id=418",
        target_price=59,
        wait_interval=5,
        operating_system="debian",
        email="buyer@example.com",
        new_customer=False,
        payment_method="paypal",
        auto_submit=True,
        password_configured=True,
    )

    assert response.password_configured is True
    assert "password" not in response.dict()
    assert "cc_num" not in response.dict()


@pytest.mark.parametrize("target_price", [0, -1, float("nan"), float("inf")])
def test_task_response_rejects_invalid_target_price(target_price):
    with pytest.raises(ValidationError):
        TaskResponse(
            id="task-1",
            goods_id="418",
            stock_url="https://nocix.net/out-of-stock/?id=418",
            cart_url="https://nocix.net/cart/?id=418",
            target_price=target_price,
            wait_interval=5,
            operating_system="debian",
            email="buyer@example.com",
            password_configured=True,
        )


@pytest.mark.parametrize("wait_interval", [0, 1, float("nan"), float("inf")])
def test_task_response_rejects_invalid_wait_interval(wait_interval):
    with pytest.raises(ValidationError):
        TaskResponse(
            id="task-1",
            goods_id="418",
            stock_url="https://nocix.net/out-of-stock/?id=418",
            cart_url="https://nocix.net/cart/?id=418",
            target_price=59,
            wait_interval=wait_interval,
            operating_system="debian",
            email="buyer@example.com",
            password_configured=True,
        )


def test_settings_require_api_key_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "encryption-key")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_require_encryption_key_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_KEY", "api-key")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("environment", ["production", "PRODUCTION", " Production "])
def test_settings_normalize_environment_before_secret_enforcement(
    monkeypatch, environment
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("API_KEY", "api-key")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_do_not_use_weak_secret_fallback(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)

    settings = Settings()

    assert settings.api_key is None
    assert settings.data_encryption_key is None


def test_settings_have_safe_non_secret_defaults(monkeypatch):
    monkeypatch.setenv("API_KEY", "api-key")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "encryption-key")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    settings = Settings()

    assert settings.browser_dsn == "http://browser:4444/wd/hub"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.data_dir == "./data"


def test_api_key_dependency_accepts_matching_key():
    settings = Settings(api_key="expected", data_encryption_key="encryption-key")

    assert require_api_key("expected", settings) is True


@pytest.mark.parametrize("provided", [None, "wrong"])
def test_api_key_dependency_rejects_missing_or_invalid_key(provided):
    settings = Settings(api_key="expected", data_encryption_key="encryption-key")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(provided, settings)

    assert exc_info.value.status_code == 401


def test_api_key_dependency_binds_header_on_protected_route():
    app = FastAPI()
    settings = Settings(api_key="expected", data_encryption_key="encryption-key")
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/protected")
    def protected(api_key=Depends(require_api_key)):
        return {"authenticated": api_key}

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            valid = await client.get(
                "/protected", headers={"X-API-Key": "expected"}
            )
            missing = await client.get("/protected")
            invalid = await client.get(
                "/protected", headers={"X-API-Key": "wrong"}
            )
        return valid, missing, invalid

    valid, missing, invalid = asyncio.run(exercise())

    assert valid.status_code == 200
    assert valid.json() == {"authenticated": True}
    assert missing.status_code == 401
    assert invalid.status_code == 401
