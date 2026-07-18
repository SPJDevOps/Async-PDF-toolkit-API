import asyncio
import io
import os
import zipfile

from fastapi import APIRouter, File, HTTPException, UploadFile
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

router = APIRouter(tags=["split"])


class _EmptyPdfError(Exception):
    """Raised when the PDF has zero pages (caller maps to HTTP 400)."""


def _split_pdf_to_zip(input_path: str, zip_path: str) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(input_path)
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise _EmptyPdfError()

        pad = len(str(page_count))
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i in range(page_count):
                new_doc = pdfium.PdfDocument.new()
                try:
                    new_doc.import_pages(pdf, [i])
                    buf = io.BytesIO()
                    new_doc.save(buf)
                    name = f"page_{i + 1:0{pad}d}.pdf"
                    zf.writestr(name, buf.getvalue())
                finally:
                    try:
                        new_doc.close()
                    except Exception:
                        pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass


@router.post("/split")
async def post_split(file: UploadFile = File(...)) -> FileResponse:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-split-")
    input_path = os.path.join(temp_dir, "input.pdf")
    zip_path = os.path.join(temp_dir, "split-pages.zip")

    async def _job() -> None:
        await file.seek(0)
        await asyncio.to_thread(save_upload_to_path, file, input_path)
        page_count = enforce_pdf_page_limit(input_path)
        if page_count == 0:
            raise _EmptyPdfError()
        await asyncio.to_thread(_split_pdf_to_zip, input_path, zip_path)

    try:
        await run_bounded_job(_job)
    except _EmptyPdfError as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(status_code=400, detail="PDF has no pages.") from exc
    except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
        cleanup_dir(temp_dir)
        raise http_for_job_error(exc, failure_prefix="PDF split failed") from exc
    except HTTPException:
        cleanup_dir(temp_dir)
        raise
    except Exception as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(status_code=500, detail=f"PDF split failed: {exc}") from exc
    finally:
        await file.close()

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="split-pages.zip",
        background=background_cleanup(temp_dir),
    )
