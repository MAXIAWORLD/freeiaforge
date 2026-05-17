from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

_EXEMPT_PATHS = frozenset({"/health", "/"})
_401_BODY = json.dumps({"detail": "Invalid or missing API key"}).encode()
_401_HEADERS = [
    [b"content-type", b"application/json"],
    [b"content-length", str(len(_401_BODY)).encode()],
]


class GatewayAuthMiddleware:
    """Pure ASGI auth middleware — streaming-safe (no response buffering).

    Enforces Authorization: Bearer <key> on all routes except /health and /.
    Disabled when api_key is None or empty string.
    """

    def __init__(self, app: ASGIApp, api_key: str | None = None) -> None:
        self.app = app
        self._api_key = api_key or ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._api_key or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        raw_auth = headers.get(b"authorization", b"").decode()
        if raw_auth.startswith("Bearer ") and raw_auth[7:] == self._api_key:
            await self.app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": _401_HEADERS,
            }
        )
        await send({"type": "http.response.body", "body": _401_BODY})
