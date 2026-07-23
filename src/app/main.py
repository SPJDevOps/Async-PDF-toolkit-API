from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.staticfiles import StaticFiles

from app.api.extract_text import router as extract_text_router
from app.api.health import router as health_router
from app.api.merge import router as merge_router
from app.api.metadata import router as metadata_router
from app.api.ocr import router as ocr_router
from app.api.qr import router as qr_router
from app.api.split import router as split_router
from app.config import get_settings
from app.middleware.api_key import ApiKeyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_UI_DIR = _STATIC_DIR / "ui"
_UI_NO_CACHE = {"Cache-Control": "no-cache"}


def _ui_asset_version() -> str:
    mtimes: list[int] = []
    for name in ("app.js", "styles.css", "index.html"):
        path = _UI_DIR / name
        if path.is_file():
            mtimes.append(path.stat().st_mtime_ns)
    return str(max(mtimes) if mtimes else 0)


_OPENAPI_DESCRIPTION = """
Async PDF toolkit: OCR, QR extraction, split, merge, native text extraction, and metadata.

- **Demo UI:** [`/`](/) — upload, run a tool, download or view results
- **OpenAPI (offline):** [`/docs`](/docs)
- **Auth:** optional. When `API_KEY` is set, send header `X-API-Key` on job endpoints.
  Leave unset for local/dev and open public demos (use tight rate/size limits instead).

Uploads are processed in temporary files and deleted after each response; nothing is retained.
""".strip()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=_OPENAPI_DESCRIPTION,
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
    )
    # Last added runs first: size guard (below) → API key → rate limit → routes.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ApiKeyMiddleware)

    @app.middleware("http")
    async def reject_oversized_content_length(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = -1
            max_bytes = get_settings().max_upload_bytes
            # Coarse guard for clearly huge bodies; per-file limits apply while saving.
            if length > max_bytes * 10:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": (
                            f"Request body exceeds maximum size of {max_bytes} bytes."
                        )
                    },
                )
        return await call_next(request)

    @app.get("/ui/app.js", include_in_schema=False)
    async def ui_app_js() -> FileResponse:
        return FileResponse(
            _UI_DIR / "app.js",
            media_type="application/javascript",
            headers=_UI_NO_CACHE,
        )

    @app.get("/ui/styles.css", include_in_schema=False)
    async def ui_styles_css() -> FileResponse:
        return FileResponse(
            _UI_DIR / "styles.css",
            media_type="text/css",
            headers=_UI_NO_CACHE,
        )

    app.mount(
        "/openapi-docs-static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="openapi_docs_static",
    )
    app.mount(
        "/ui",
        StaticFiles(directory=str(_UI_DIR)),
        name="ui",
    )

    @app.get("/", include_in_schema=False)
    async def demo_ui() -> HTMLResponse:
        html = (_UI_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__UI_ASSET_V__", _ui_asset_version())
        return HTMLResponse(content=html, headers=_UI_NO_CACHE)

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="/openapi-docs-static/swagger-ui/swagger-ui-bundle.js",
            swagger_css_url="/openapi-docs-static/swagger-ui/swagger-ui.css",
            swagger_favicon_url="",
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    async def swagger_ui_redirect() -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()

    app.include_router(health_router)
    app.include_router(ocr_router)
    app.include_router(qr_router)
    app.include_router(split_router)
    app.include_router(merge_router)
    app.include_router(extract_text_router)
    app.include_router(metadata_router)
    return app


app = create_app()
