import asyncio
import os
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.pdf_jobs import (
    UploadTooLargeError,
    TooManyPagesError,
    cleanup_dir,
    enforce_pdf_page_limit,
    http_for_job_error,
    make_job_tempdir,
    pdf_page_count,
    run_bounded_job,
    save_upload_to_path,
    validate_pdf_upload,
)

router = APIRouter(tags=["metadata"])


def _has_native_text(input_path: str) -> bool:
    """Return True if any page has a non-empty native text layer."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return False
    try:
        pdf = pdfium.PdfDocument(input_path)
    except Exception:
        return False
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    if textpage.count_chars() > 0:
                        return True
                finally:
                    try:
                        textpage.close()
                    except Exception:
                        pass
            except Exception:
                pass
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
    return False


def _collect_form_fields(fields: Any) -> list[Any]:
    """Flatten AcroForm /Fields, following /Kids for hierarchical fields."""
    collected: list[Any] = []
    for field in fields:
        collected.append(field)
        kids = field.get("/Kids")
        if kids is not None:
            collected.extend(_collect_form_fields(kids))
    return collected


def _pikepdf_metadata(input_path: str) -> dict[str, Any]:
    """Best-effort encryption/version/info/signature metadata via pikepdf."""
    result: dict[str, Any] = {
        "is_encrypted": False,
        "pdf_version": None,
        "has_form_fields": False,
        "has_signature_fields": False,
        "is_signed": False,
        "info": {},
    }
    try:
        import pikepdf
    except Exception:
        return result

    try:
        pdf = pikepdf.open(input_path)
    except pikepdf.PasswordError:
        result["is_encrypted"] = True
        return result
    except Exception:
        return result

    try:
        result["is_encrypted"] = pdf.is_encrypted
        result["pdf_version"] = str(pdf.pdf_version)

        try:
            docinfo = pdf.docinfo
            result["info"] = {
                str(key).lstrip("/").lower(): str(value)
                for key, value in docinfo.items()
            }
        except Exception:
            pass

        try:
            acroform = pdf.Root.get("/AcroForm")
            if acroform is not None:
                fields = _collect_form_fields(acroform.get("/Fields", []))
                result["has_form_fields"] = len(fields) > 0
                sig_fields = [f for f in fields if f.get("/FT") == pikepdf.Name("/Sig")]
                result["has_signature_fields"] = len(sig_fields) > 0
                result["is_signed"] = any(
                    f.get("/V") is not None for f in sig_fields
                )
        except Exception:
            pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass

    return result


def _extract_metadata(input_path: str, *, filename: str, file_size_bytes: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "filename": filename,
        "file_size_bytes": file_size_bytes,
        "page_count": pdf_page_count(input_path),
        "has_text": _has_native_text(input_path),
    }
    metadata.update(_pikepdf_metadata(input_path))
    return metadata


@router.post("/metadata")
async def post_metadata(file: UploadFile = File(...)) -> dict[str, Any]:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-metadata-")
    input_path = os.path.join(temp_dir, "input.pdf")

    async def _job() -> dict[str, Any]:
        await file.seek(0)
        size = await asyncio.to_thread(save_upload_to_path, file, input_path)
        enforce_pdf_page_limit(input_path)
        return await asyncio.to_thread(
            _extract_metadata,
            input_path,
            filename=file.filename or "",
            file_size_bytes=size,
        )

    try:
        return await run_bounded_job(_job)
    except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
        raise http_for_job_error(exc, failure_prefix="Metadata extraction failed") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Metadata extraction failed: {exc}"
        ) from exc
    finally:
        cleanup_dir(temp_dir)
        await file.close()
