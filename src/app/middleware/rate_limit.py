"""Lightweight per-IP rate limiting (in-memory; single-replica only)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.limits import check_rate_limit

_SKIP_PREFIXES = (
    "/",
    "/health",
    "/ui",
    "/docs",
    "/openapi.json",
    "/openapi-docs-static",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _SKIP_PREFIXES):
            return await call_next(request)

        client_ip = "unknown"
        if request.client is not None:
            client_ip = request.client.host

        allowed = await check_rate_limit(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
        return await call_next(request)
