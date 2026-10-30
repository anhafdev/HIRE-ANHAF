from __future__ import annotations

from typing import Any

import httpx

from ..exceptions import ProviderCallFailed

DEFAULT_HEADERS = {"User-Agent": "cryptoverify/1.0", "Accept": "application/json"}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpSession:
    def __init__(self, timeout_seconds: float = 8.0, max_connections: int = 20, client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=10),
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def fetch_json(
        self,
        provider: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_missing: bool = False,
    ) -> Any:
        return await self._deliver(provider, "GET", url, params=params, headers=headers, allow_missing=allow_missing)

    async def send_json(
        self,
        provider: str,
        url: str,
        payload: dict[str, Any] | list[Any],
        headers: dict[str, str] | None = None,
        allow_missing: bool = False,
    ) -> Any:
        return await self._deliver(provider, "POST", url, json_body=payload, headers=headers, allow_missing=allow_missing)

    async def _deliver(
        self,
        provider: str,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        allow_missing: bool = False,
    ) -> Any:
        try:
            response = await self._client.request(method, url, params=params, json=json_body, headers=headers)
        except httpx.TimeoutException as error:
            raise ProviderCallFailed(provider, f"network timeout ({error})", retryable=True)
        except httpx.HTTPError as error:
            raise ProviderCallFailed(provider, f"connection problem ({type(error).__name__})", retryable=True)

        if allow_missing and response.status_code in (404, 400):
            return None
        if response.status_code >= 400:
            raise ProviderCallFailed(
                provider,
                f"http {response.status_code}",
                retryable=response.status_code in RETRYABLE_STATUS,
            )
        text = response.text.strip()
        if not text:
            return None
        try:
            return response.json()
        except Exception:
            raise ProviderCallFailed(provider, "response was not valid json", retryable=False)

    async def close(self) -> None:
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()
