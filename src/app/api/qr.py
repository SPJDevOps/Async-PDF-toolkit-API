import asyncio
import os

from fastapi import APIRouter, File, UploadFile

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

router = APIRouter(tags=["qr"])


def _extract_qr_codes(input_path: str) -> list[str]:
    """Return decoded QR text for each code found, or an empty list on any failure.

    Heavy deps are imported here so the app can load in environments where zbar
    is not installed (e.g. dev machines); those runs simply yield [].
    """
    try:
        import pypdfium2 as pdfium
        from pyzbar.pyzbar import ZBarSymbol, decode
    except Exception:  # pragma: no cover - import when libzbar missing
        return []

    results: list[str] = []
    try:
        pdf = pdfium.PdfDocument(input_path)
    except Exception:
        return []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                render = page.render(scale=2.0)
                try:
                    image = render.to_pil()
                    for sym in decode(image, symbols=[ZBarSymbol.QRCODE]):
                        results.append(sym.data.decode("utf-8", errors="replace"))
                except Exception:
                    pass
                finally:
                    render.close()
            except Exception:
                pass
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    except Exception:
        return []
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return results


@router.post("/qr")
async def post_qr(file: UploadFile = File(...)) -> dict[str, list[str]]:
    validate_pdf_upload(file)

    temp_dir = make_job_tempdir("ocr-api-qr-")
    input_path = os.path.join(temp_dir, "input.pdf")
    try:

        async def _job() -> list[str]:
            try:
                await file.seek(0)
                await asyncio.to_thread(save_upload_to_path, file, input_path)
            except UploadTooLargeError:
                raise
            except Exception:
                return []
            try:
                enforce_pdf_page_limit(input_path)
            except TooManyPagesError:
                raise
            try:
                return await asyncio.to_thread(_extract_qr_codes, input_path)
            except Exception:
                return []

        try:
            results = await run_bounded_job(_job)
        except (UploadTooLargeError, TooManyPagesError, TimeoutError) as exc:
            raise http_for_job_error(exc, failure_prefix="QR scan failed") from exc
        return {"qr_codes": results}
    finally:
        cleanup_dir(temp_dir)
        await file.close()
