from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.main import app
from app.services.limits import reset_limit_state


def test_upload_rejects_when_over_max_bytes(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "100")
    clear_settings_cache()
    reset_limit_state()

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={
            "file": (
                "sample.pdf",
                b"%PDF-1.4\n" + b"x" * 200,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert "maximum size" in response.json()["detail"]


def test_extract_text_rejects_too_many_pages(monkeypatch) -> None:
    import io

    import pypdfium2 as pdfium

    monkeypatch.setenv("MAX_PDF_PAGES", "1")
    clear_settings_cache()
    reset_limit_state()

    doc = pdfium.PdfDocument.new()
    try:
        doc.new_page(100, 100)
        doc.new_page(100, 100)
        buf = io.BytesIO()
        doc.save(buf)
        pdf_bytes = buf.getvalue()
    finally:
        doc.close()

    client = TestClient(app)
    response = client.post(
        "/extract-text",
        files={"file": ("two.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 400
    assert "maximum allowed is 1" in response.json()["detail"]
