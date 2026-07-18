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
) -> None:
    import ocrmypdf

    options: dict[str, Any] = {
        "deskew": deskew,
        "force_ocr": force_ocr,
    }
    if language:
        options["language"] = language
    if optimize is not None:
        options["optimize"] = optimize

    ocrmypdf.ocr(input_path, output_path, **options)


@router.post("/ocr")
async def post_ocr(
    file: UploadFile = File(...),
    language: str | None = Query(default=None, min_length=2, max_length=32),
    deskew: bool = Query(default=False),
    force_ocr: bool = Query(default=False),
    optimize: int | None = Query(default=None, ge=0, le=3),
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
