from functools import lru_cache

import pydantic
import pydantic.error_wrappers
from loguru import logger

from nocix_fucker import types
from nocix_fucker.logic import redact_config


def missing_new_customer_info() -> None:
    raise ValueError("field required if you are new customer")


def missing_existing_customer_info() -> None:
    raise ValueError("field required if you are existing customer")


def missing_credit_card_info() -> None:
    raise ValueError("field required if you are using credit card payment method")


class ProxyDsn(pydantic.AnyUrl):
    allowed_schemes = {"socks4", "socks5", "http"}

    @property
    def dict(self) -> dict:
        data = {
            "proxyType": "MANUAL",
        }

        host_port = f"{self.host}:{self.port}"

        if self.scheme == "http":
            data["httpProxy"] = host_port
            data["sslProxy"] = host_port
        else:
            data["socksProxy"] = host_port
            data["socksUsername"] = self.user
            data["socksPassword"] = self.password

            if "4" in self.scheme:
                data["socksVersion"] = "4"
            else:
                data["socksVersion"] = "5"

        return data


class Config(pydantic.BaseSettings):
    browser_dsn: pydantic.AnyUrl
    proxy_dsn: ProxyDsn | None = None

    goods_id: str = "418"
    target_price: float
    wait_interval: float = 5.0

    new_customer: bool
    payment_method: types.PaymentMethod

    cc_num: str | None
    cc_exp_month: str | None
    cc_exp_year: str | None
    cc_ccv: str | None

    email: pydantic.EmailStr
    password: str | None
    first_name: str | None
    last_name: str | None
    company: str | None
    phone: str | None
    address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country_name: str | None

    @pydantic.validator("cc_num")
    def check_cc_num(cls, value, values, **kwargs):
        if not value and values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
            missing_credit_card_info()

        return value

    @pydantic.validator("cc_exp_month")
    def check_cc_exp_month(cls, value, values, **kwargs):
        if not value:
            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("cc_exp_year")
    def check_cc_exp_year(cls, value, values, **kwargs):
        if not value and values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
            missing_credit_card_info()

        return value

    @pydantic.validator("cc_ccv")
    def check_cc_ccv(cls, value, values, **kwargs):
        if not value and values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
            missing_credit_card_info()

        return value

    @pydantic.validator("password")
    def check_password(cls, value, values, **kwargs):
        if not value and not values.get("new_customer", True):
            missing_existing_customer_info()

        return value

    @pydantic.validator("first_name")
    def check_first_name(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("last_name")
    def check_last_name(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("company")
    def check_company(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("phone")
    def check_phone(cls, value, values, **kwargs):
        if not value and values.get("new_customer", True):
            missing_new_customer_info()

        return value

    @pydantic.validator("address")
    def check_address(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("city")
    def check_city(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("state")
    def check_state(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("postal_code")
    def check_postal_code(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value

    @pydantic.validator("country_name")
    def check_country_name(cls, value, values, **kwargs):
        if not value:
            if values.get("new_customer", True):
                missing_new_customer_info()

            if values.get("payment_method") == types.PaymentMethod.CREDIT_CARD:
                missing_credit_card_info()

        return value


def format_config_summary(config: dict) -> list[str]:
    lines = []
    for key, value in config.items():
        lines.append(f"{key}: {value}")
    return lines


def print_config_summary(config: dict) -> None:
    logger.debug("Config summary:")
    for line in format_config_summary(redact_config(config)):
        logger.debug(f"    {line}")


def format_validation_errors(errors: list) -> list[str]:
    lines = []
    for error in errors:
        loc = error["loc"][0]
        err_msg = error["msg"]

        lines.append(f"{loc}: {err_msg}")
    return lines


def print_config_errors(errors: list) -> None:
    logger.error("Missing or incorrect field from environment:")
    for line in format_validation_errors(errors):
        logger.error(f"    {line}")


@lru_cache()
def get_config() -> Config | None:
    logger.info("Loading config from environment")
    try:
        cfg = Config()
        print_config_summary(cfg.dict())
    except pydantic.error_wrappers.ValidationError as exc:
        cfg = None
        print_config_errors(exc.errors())
    return cfg
