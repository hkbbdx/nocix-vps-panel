import re
from typing import Any


REDACTION_MARKER = "***REDACTED***"

_SENSITIVE_KEY = (
    r"(?:password|cc_num|cc_ccv|cc_exp_month|cc_exp_year|token|cookie|"
    r"authorization|card|card_number|card_no|card_cvv|cvv|cvc|security_code|"
    r"card_expiry|card_exp_month|card_exp_year|expiry|expiration|"
    r"access_token|refresh_token|api_key|client_secret|client_secret_key|"
    r"secret_key|bot_token|session_token|auth_token|private_key|"
    r"proxy_url(?:_ciphertext)?|"
    r"paypal[\w-]*|session[\w-]*)"
)
_KEY_PATTERN = re.compile(
    rf"(?<![\w-])(?P<key_quote>['\"]?)(?P<key>{_SENSITIVE_KEY})"
    rf"(?P=key_quote)(?![\w-])(?P<separator>\s*[:=]\s*)",
    re.IGNORECASE,
)
_PROXY_URL_PATTERN = re.compile(
    r"(?P<scheme>https?://|socks5://)"
    r"(?P<userinfo>[^/\s]+@)"
    r"(?P<host>\[[^\]\s]+\]|[^:/\s@]+):(?P<port>[0-9]{1,5})",
    re.IGNORECASE,
)


def _quoted_value_end(text: str, start: int, quote: str) -> int:
    escaped = False
    for index in range(start + 1, len(text)):
        character = text[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            return index + 1
    return len(text)


def _value_end(text: str, start: int) -> int:
    if start >= len(text):
        return start
    if text[start] in {"'", '"'}:
        return _quoted_value_end(text, start, text[start])

    index = start
    while index < len(text) and not text[index].isspace() and text[index] not in ",}]":
        index += 1
    return index


def redact_message(message: Any) -> str:
    text = _PROXY_URL_PATTERN.sub(
        lambda match: (
            f"{match.group('scheme')}"
            f"{match.group('host')}:{match.group('port')}"
        ),
        str(message),
    )
    output: list[str] = []
    cursor = 0

    for match in _KEY_PATTERN.finditer(text):
        if match.start() < cursor:
            continue
        value_start = match.end()
        value_end = _value_end(text, value_start)
        quote = text[value_start] if value_start < len(text) and text[value_start] in {"'", '"'} else ""
        output.append(text[cursor:value_start])
        output.append(quote + REDACTION_MARKER + quote)
        cursor = value_end

    output.append(text[cursor:])
    return "".join(output)
