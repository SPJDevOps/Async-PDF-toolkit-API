import asyncio
import os

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

router = APIRouter(tags=["to-image"])


class _EmptyPdfError(Exception):
    """Raised when the PDF has zero pages (caller maps to HTTP 400)."""


class _PageOutOfRangeError(Exception):
    """Raised when the requested page is outside the PDF page count."""

    def __init__(self, page: int, page_count: int) -> None:
        self.page = page
        self.page_count = page_count
        super().__init__(
            f"Page {page} is out of range (PDF has {page_count} pages)."
        )


def _render_page_to_png(
    input_path: str,
    output_path: str,
    *,
    dpi: int,
    page: int,
) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(input_path)
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise _EmptyPdfError()
        if page > page_count:
            raise _PageOutOfRangeError(page, page_count)

        pdf_page = pdf[page - 1]
        try:
            # PDF user space is 72 DPI; scale so rendered pixels match requested dpi.
            scale = dpi / 72.0
            bitmap = pdf_page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                image.save(output_path, format="PNG")
            finally:
                bitmap.close()
        finally:
            try:
                pdf_page.close()
            except Exception:
                pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass


@router.post("/to-image")
async def post_to_image(
    file: UploadFile = File(...),
    dpi: int = Query(
        default=300,
        ge=72,
        le=600,
        description="Render resolution in dots per inch (default 300).",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="1-based page number to render (default 1).",
    ),
) -> FileResponse:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-to-image-")
    input_path = os.path.join(temp_dir, "input.pdf")
    output_path = os.path.join(temp_dir, f"page-{page}.png")

    async def _job() -> None:
        await file.seek(0)
        await asyncio.to_thread(save_upload_to_path, file, input_path)
        page_count = enforce_pdf_page_limit(input_path)
        if page_count == 0:
            raise _EmptyPdfError()
        await asyncio.to_thread(
            _render_page_to_png,
            input_path,
            output_path,
            dpi=dpi,
            page=page,
        )

    try:
        await run_bounded_job(_job)
    except _EmptyPdfError as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(status_code=400, detail="PDF has no pages.") from exc
    except _PageOutOfRangeError as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
        cleanup_dir(temp_dir)
        raise http_for_job_error(exc, failure_prefix="PDF to image failed") from exc
    except HTTPException:
        cleanup_dir(temp_dir)
        raise
    except Exception as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(
            status_code=500, detail=f"PDF to image failed: {exc}"
        ) from exc
    finally:
        await file.close()

    return FileResponse(
        output_path,
        media_type="image/png",
        filename=f"page-{page}.png",
        background=background_cleanup(temp_dir),
    )
