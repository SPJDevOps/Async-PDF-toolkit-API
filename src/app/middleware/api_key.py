"""Optional API key gate via X-API-Key (disabled when API_KEY is unset)."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

_PROTECTED_PREFIXES = (
    "/ocr",
    "/qr",
    "/split",
    "/merge",
    "/extract-text",
    "/metadata",
)


def _is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _PROTECTED_PREFIXES)


def _keys_match(provided: str, expected: str) -> bool:
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        expected = get_settings().api_key
        if not expected:
            return await call_next(request)

        if not _is_protected(request.url.path):
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if not _keys_match(provided, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )
        return await call_next(request)
