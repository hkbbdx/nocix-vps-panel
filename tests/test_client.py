from types import SimpleNamespace

from loguru import logger

from nocix_fucker.client import Client


def build_client(current_url):
    client = Client.__new__(Client)
    client._driver = SimpleNamespace(
        current_url=current_url,
        get=lambda url: None,
    )
    client._find_element = lambda *args, **kwargs: SimpleNamespace(text="in stock")
    return client


def test_client_url_logs_redact_query_and_fragment(monkeypatch):
    messages = []
    sink_id = logger.add(messages.append, format="{message}", level="TRACE")
    client = build_client(
        "https://shop.nocix.net/stock/item?token=secret-token#secret-fragment"
    )

    try:
        client.check_stock(
            "418",
            "https://shop.nocix.net/stock/item?token=configured-token#fragment",
        )
        client.open_cart(
            "418",
            "https://shop.nocix.net/cart/item?token=configured-token#fragment",
        )
    finally:
        logger.remove(sink_id)

    output = " ".join(messages)
    assert "configured-token" not in output
    assert "secret-token" not in output
    assert "fragment" not in output
    assert "https://shop.nocix.net/stock/item" in output
    assert "https://shop.nocix.net/cart/item" in output
