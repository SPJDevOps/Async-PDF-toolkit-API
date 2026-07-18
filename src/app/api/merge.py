import asyncio
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.pdf_jobs import (
    UploadTooLargeError,
    TooManyPagesError,
    background_cleanup,
    cleanup_dir,
    http_for_job_error,
    make_job_tempdir,
    pdf_page_count,
    run_bounded_job,
    save_upload_to_path,
    validate_pdf_upload,
)

router = APIRouter(tags=["merge"])


def _merge_pdfs(input_paths: list[str], output_path: str) -> None:
    import pypdfium2 as pdfium

    merged = pdfium.PdfDocument.new()
    opened: list[object] = []
    try:
        for path in input_paths:
            src = pdfium.PdfDocument(path)
            opened.append(src)
            if len(src) == 0:
                continue
            merged.import_pages(src, list(range(len(src))))
        if len(merged) == 0:
            raise ValueError("Merged PDF has no pages.")
        merged.save(output_path)
    finally:
        for src in opened:
            try:
                src.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            merged.close()
        except Exception:
            pass


@router.post("/merge")
async def post_merge(
    files: list[UploadFile] = File(...),
) -> FileResponse:
    if len(files) < 2:
        raise HTTPException(
            status_code=400, detail="At least two PDF files are required."
        )

    for upload in files:
        validate_pdf_upload(upload)

    settings = get_settings()
    temp_dir = make_job_tempdir("ocr-api-merge-")
    output_path = os.path.join(temp_dir, "merged.pdf")
    input_paths: list[str] = []

    async def _job() -> None:
        total_pages = 0
        for index, upload in enumerate(files):
            path = os.path.join(temp_dir, f"input_{index}.pdf")
            await upload.seek(0)
            await asyncio.to_thread(save_upload_to_path, upload, path)
            input_paths.append(path)
            count = pdf_page_count(path)
            if count is not None:
                total_pages += count
                if total_pages > settings.max_pdf_pages:
                    raise TooManyPagesError(
                        f"Merged PDF would have at least {total_pages} pages; "
                        f"maximum allowed is {settings.max_pdf_pages}."
                    )
        await asyncio.to_thread(_merge_pdfs, input_paths, output_path)

    try:
        await run_bounded_job(_job)
    except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
        cleanup_dir(temp_dir)
        raise http_for_job_error(exc, failure_prefix="PDF merge failed") from exc
    except HTTPException:
        cleanup_dir(temp_dir)
        raise
    except Exception as exc:
        cleanup_dir(temp_dir)
        raise HTTPException(status_code=500, detail=f"PDF merge failed: {exc}") from exc
    finally:
        for upload in files:
            await upload.close()

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename="merged.pdf",
        background=background_cleanup(temp_dir),
    )
