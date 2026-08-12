from decimal import Decimal, InvalidOperation
import re
from typing import Any


SENSITIVE_CONFIG_KEYS = {
    "password",
    "cc_num",
    "cc_exp_month",
    "cc_exp_year",
    "cc_ccv",
    "proxy_dsn",
}


def is_in_stock(page_text: str, current_url: str) -> bool:
    normalized_text = " ".join(page_text.lower().split())
    normalized_url = current_url.lower()

    if "out of stock" in normalized_text:
        return False
    if "/out-of-stock/" in normalized_url:
        return False
    return True


def prices_match(actual_text: str, target_price: float) -> bool:
    try:
        match = re.search(r"\d[\d,]*(?:\.\d+)?", actual_text)
        if match is None:
            return False
        actual = Decimal(match.group(0).replace(",", ""))
        target = Decimal(str(target_price))
    except (InvalidOperation, ValueError):
        return False

    return actual.quantize(Decimal("0.01")) == target.quantize(Decimal("0.01"))


def redact_config(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "***REDACTED***" if key in SENSITIVE_CONFIG_KEYS else value
        for key, value in values.items()
    }
