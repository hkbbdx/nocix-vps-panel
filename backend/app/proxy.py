from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit


"""Strict proxy URL parsing for HTTP and SOCKS5 endpoints.

Proxy DNS names intentionally use ASCII hostname syntax only. Internationalized
names must be converted to their ASCII IDNA form before they reach this boundary.
"""


class ProxyValidationError(ValueError):
    """Raised when a proxy URL is not safe to persist or use."""


@dataclass(frozen=True)
class ProxyConfig:
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def safe_display(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"

    @property
    def has_credentials(self) -> bool:
        return self.username is not None


_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _decode_userinfo(value: str) -> str:
    if "@" in value:
        raise ProxyValidationError("invalid proxy URL")
    index = 0
    while index < len(value):
        if value[index] == "%":
            if not _PERCENT_ESCAPE.match(value, index):
                raise ProxyValidationError("invalid proxy URL")
            index += 3
        else:
            index += 1
    try:
        decoded = unquote(value, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProxyValidationError("invalid proxy URL") from exc
    if not decoded or any(character.isspace() for character in decoded) or _contains_control(decoded):
        raise ProxyValidationError("invalid proxy URL")
    return decoded


def _validate_host(host: str) -> str:
    normalized = host.lower()
    if (
        not normalized
        or any(character.isspace() for character in normalized)
        or _contains_control(normalized)
        or "%" in normalized
    ):
        raise ProxyValidationError("invalid proxy URL")
    if normalized == "localhost":
        raise ProxyValidationError("invalid proxy URL")
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            normalized.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ProxyValidationError("invalid proxy URL") from exc
        if (
            re.fullmatch(r"[0-9.]+", normalized)
            or re.fullmatch(r"0[xX][0-9A-Fa-f]+", normalized)
        ):
            raise ProxyValidationError("invalid proxy URL")
        if len(normalized) > 253:
            raise ProxyValidationError("invalid proxy URL")
        labels = normalized.split(".")
        if any(not label or len(label) > 63 or not _DNS_LABEL.fullmatch(label) for label in labels):
            raise ProxyValidationError("invalid proxy URL")
        return normalized
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
    ):
        raise ProxyValidationError("invalid proxy URL")
    return normalized


def parse_proxy_url(value: str) -> ProxyConfig:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
        or _contains_control(value)
    ):
        raise ProxyValidationError("invalid proxy URL")
    index = 0
    while index < len(value):
        if value[index] == "%":
            if not _PERCENT_ESCAPE.match(value, index):
                raise ProxyValidationError("invalid proxy URL")
            index += 3
        else:
            index += 1
    if not value.startswith(("http://", "socks5://")):
        raise ProxyValidationError("invalid proxy URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ProxyValidationError("invalid proxy URL") from exc
    if (
        parsed.scheme not in {"http", "socks5"}
        or not parsed.netloc
        or not hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port is None
        or not 1 <= port <= 65535
    ):
        raise ProxyValidationError("invalid proxy URL")

    if parsed.username is None and parsed.password is None:
        username = password = None
    elif parsed.username is None or parsed.password is None:
        raise ProxyValidationError("invalid proxy URL")
    else:
        username = _decode_userinfo(parsed.username)
        password = _decode_userinfo(parsed.password)

    return ProxyConfig(
        scheme=parsed.scheme,
        host=_validate_host(hostname),
        port=port,
        username=username,
        password=password,
    )
