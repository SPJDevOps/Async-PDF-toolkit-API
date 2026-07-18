import asyncio
import os

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.services.pdf_jobs import (
    UploadTooLargeError,
    TooManyPagesError,
    cleanup_dir,
    enforce_pdf_page_limit,
    http_for_job_error,
    make_job_tempdir,
    run_bounded_job,
    save_upload_to_path,
    validate_pdf_upload,
)

router = APIRouter(tags=["extract-text"])


def _extract_text_pages(input_path: str) -> list[str]:
    """Return native text per page; empty strings when no text is present."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []

    try:
        pdf = pdfium.PdfDocument(input_path)
    except Exception:
        return []

    pages: list[str] = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_bounded() or ""
                except Exception:
                    text = ""
                finally:
                    try:
                        textpage.close()
                    except Exception:
                        pass
                pages.append(text)
            except Exception:
                pages.append("")
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return pages


@router.post("/extract-text")
async def post_extract_text(
    file: UploadFile = File(...),
    join_pages: bool = Query(default=True),
) -> dict[str, str | list[str]]:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-extract-")
    input_path = os.path.join(temp_dir, "input.pdf")

    async def _job() -> list[str]:
        await file.seek(0)
        await asyncio.to_thread(save_upload_to_path, file, input_path)
        enforce_pdf_page_limit(input_path)
        return await asyncio.to_thread(_extract_text_pages, input_path)

    try:
        pages = await run_bounded_job(_job)
    except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
        raise http_for_job_error(exc, failure_prefix="Text extraction failed") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Text extraction failed: {exc}"
        ) from exc
    finally:
        cleanup_dir(temp_dir)
        await file.close()

    if join_pages:
        return {"text": "\n".join(pages)}
    return {"pages": pages}
