from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..proxy import ProxyValidationError, parse_proxy_url
from ..security import require_api_key


router = APIRouter(prefix="/api/proxy", dependencies=[Depends(require_api_key)])


class ProxyTestRequest(BaseModel):
    proxy_url: str | None = None


@router.post("/test")
async def test_proxy(request: Request, body: ProxyTestRequest | None = None):
    repository = request.app.state.repository
    proxy = None
    client = None
    if body and body.proxy_url:
        try:
            proxy = parse_proxy_url(body.proxy_url)
        except ProxyValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid proxy URL") from exc
    try:
        if proxy is None:
            proxy = repository.get_global_proxy()
        if proxy is None:
            return {
                "success": True,
                "proxy": "direct",
                "message": "No proxy configured; direct connection selected.",
            }
        factory = getattr(request.app.state, "proxy_test_client_factory", None)
        if factory is None:
            from nocix_fucker.client import Client

            client = Client(request.app.state.settings.browser_dsn, proxy)
        else:
            client = factory(proxy)
        client.test_connection("https://example.com/")
        return {
            "success": True,
            "proxy": proxy.safe_display,
            "message": "Proxy connection successful.",
        }
    except Exception:
        return {
            "success": False,
            "proxy": proxy.safe_display if proxy is not None else "direct",
            "message": (
                "Proxy test unavailable; direct connection selected."
                if proxy is None
                else "Proxy connection failed."
            ),
        }
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
