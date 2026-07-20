import asyncio
import os
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.services.pdf_jobs import (
    UploadTooLargeError,
    TooManyPagesError,
    background_cleanup,
    cleanup_dir,
    enforce_pdf_page_limit,
    http_for_job_error,
    make_job_tempdir,
    run_bounded_job,
    save_upload_to_path,
    validate_pdf_upload,
)

router = APIRouter(tags=["ocr"])


def _run_ocr(
    input_path: str,
    output_path: str,
    *,
    language: str | None,
    deskew: bool,
    force_ocr: bool,
    optimize: int | None,
    rotate_pages: bool,
    skip_text: bool,
    clean: bool,
    remove_background: bool,
) -> None:
    import ocrmypdf

    options: dict[str, Any] = {
        "deskew": deskew,
        "force_ocr": force_ocr,
        "rotate_pages": rotate_pages,
        "skip_text": skip_text,
        "clean": clean,
        "remove_background": remove_background,
    }
    if language:
        options["language"] = language
    if optimize is not None:
        options["optimize"] = optimize

    ocrmypdf.ocr(input_path, output_path, **options)


@router.post("/ocr")
async def post_ocr(
    file: UploadFile = File(...),
    language: str | None = Query(
        default=None,
        min_length=2,
        max_length=32,
        description="Tesseract OCR language code(s), e.g. 'eng' or 'eng+deu' for multiple.",
    ),
    deskew: bool = Query(
        default=False, description="Deskew (straighten) each page before OCR."
    ),
    force_ocr: bool = Query(
        default=False,
        description=(
            "Rasterize and OCR every page, discarding any existing "
            "text/vector content. Mutually exclusive with skip_text."
        ),
    ),
    optimize: int | None = Query(
        default=None,
        ge=0,
        le=3,
        description=(
            "Post-OCR PDF optimization level: 0 = none, 1 = safe lossless "
            "(default), 2 = lossy JPEG/JPEG2000 recompression, "
            "3 = more aggressive lossy recompression."
        ),
    ),
    rotate_pages: bool = Query(
        default=False,
        description="Automatically rotate pages based on detected text orientation.",
    ),
    skip_text: bool = Query(
        default=False,
        description=(
            "Skip OCR on pages that already contain text, but keep them in "
            "the output. Mutually exclusive with force_ocr."
        ),
    ),
    clean: bool = Query(
        default=False,
        description=(
            "Clean scanning artifacts (via unpaper) before OCR to improve "
            "accuracy; the cleaned image is not included in the final output."
        ),
    ),
    remove_background: bool = Query(
        default=False,
        description="Remove gray/color background from scanned pages, setting it to white.",
    ),
) -> FileResponse:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-")
    input_path = os.path.join(temp_dir, "input.pdf")
    output_path = os.path.join(temp_dir, "output.pdf")

    async def _job() -> None:
        await file.seek(0)
        await asyncio.to_thread(save_upload_to_path, file, input_path)
        try:
            enforce_pdf_page_limit(input_path)
        except TooManyPagesError:
            raise
        await asyncio.to_thread(
            _run_ocr,
            input_path,
            output_path,
            language=language,
            deskew=deskew,
            force_ocr=force_ocr,
            optimize=optimize,
            rotate_pages=rotate_pages,
            skip_text=skip_text,
            clean=clean,
            remove_background=remove_background,
        )

    try:
        await run_bounded_job(_job)
    except (UploadTooLargeError, TooManyPagesError, TimeoutError, Exception) as exc:
        cleanup_dir(temp_dir)
        if isinstance(exc, (UploadTooLargeError, TooManyPagesError, TimeoutError)):
            raise http_for_job_error(
                exc, failure_prefix="OCR processing failed"
            ) from exc
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500, detail=f"OCR processing failed: {exc}"
        ) from exc
    finally:
        await file.close()

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename="ocr-output.pdf",
        background=background_cleanup(temp_dir),
    )
