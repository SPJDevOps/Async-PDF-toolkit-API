"""Shared upload, temp-dir, and PDF limit helpers for job endpoints."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from typing import TypeVar
from pathlib import Path

from fastapi import HTTPException, UploadFile
from starlette.background import BackgroundTask

from app.config import get_settings
from app.services.limits import acquire_job_slot, release_job_slot

T = TypeVar("T")


class UploadTooLargeError(Exception):
    """Raised when an upload exceeds MAX_UPLOAD_BYTES."""


class TooManyPagesError(Exception):
    """Raised when a PDF exceeds MAX_PDF_PAGES."""


def validate_pdf_upload(file: UploadFile) -> None:
    has_pdf_filename = bool(file.filename and file.filename.lower().endswith(".pdf"))
    if file.content_type != "application/pdf" and not has_pdf_filename:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")


def make_job_tempdir(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def background_cleanup(temp_dir: str) -> BackgroundTask:
    return BackgroundTask(cleanup_dir, temp_dir)


def save_upload_to_path(
    upload: UploadFile, path: str, *, max_bytes: int | None = None
) -> int:
    """Write upload to disk; raise UploadTooLargeError if over max_bytes."""
    limit = max_bytes if max_bytes is not None else get_settings().max_upload_bytes
    written = 0
    with Path(path).open("wb") as output_file:
        while True:
            chunk = upload.file.read(1024 * 64)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                raise UploadTooLargeError(
                    f"Upload exceeds maximum size of {limit} bytes."
                )
            output_file.write(chunk)
    return written


def pdf_page_count(path: str) -> int | None:
    """Return page count, or None if the file cannot be opened as a PDF."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception:
        return None
    try:
        return len(pdf)
    finally:
        try:
            pdf.close()
        except Exception:
            pass


def enforce_pdf_page_limit(
    path: str, *, max_pages: int | None = None, label: str = "PDF"
) -> int | None:
    """Enforce MAX_PDF_PAGES when the PDF is readable.

    Returns the page count when known, or None if the file could not be opened
    (callers may still attempt processing).
    """
    limit = max_pages if max_pages is not None else get_settings().max_pdf_pages
    count = pdf_page_count(path)
    if count is None:
        return None
    if count > limit:
        raise TooManyPagesError(
            f"{label} has {count} pages; maximum allowed is {limit}."
        )
    return count


def http_for_job_error(exc: BaseException, *, failure_prefix: str) -> HTTPException:
    if isinstance(exc, UploadTooLargeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TooManyPagesError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=504, detail="Processing timed out.")
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=500, detail=f"{failure_prefix}: {exc}")


async def run_bounded_job(work: Callable[[], Awaitable[T]]) -> T:
    """Run async work under the global job semaphore and job timeout."""
    settings = get_settings()
    await acquire_job_slot()
    try:
        return await asyncio.wait_for(work(), timeout=settings.job_timeout_seconds)
    finally:
        release_job_slot()
