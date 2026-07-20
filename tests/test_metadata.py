import io

import pypdfium2 as pdfium
from fastapi.testclient import TestClient

from app.main import app


def _blank_pdf_bytes() -> bytes:
    doc = pdfium.PdfDocument.new()
    try:
        doc.new_page(200, 200)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    finally:
        doc.close()


def test_metadata_returns_extracted_fields(monkeypatch) -> None:
    def fake_extract(_input_path: str, *, filename: str, file_size_bytes: int) -> dict:
        return {
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "page_count": 3,
            "has_text": True,
            "is_encrypted": False,
            "pdf_version": "1.7",
            "has_form_fields": True,
            "has_signature_fields": True,
            "is_signed": True,
            "info": {"title": "Example"},
        }

    monkeypatch.setattr("app.api.metadata._extract_metadata", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/metadata",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "sample.pdf"
    assert body["page_count"] == 3
    assert body["has_signature_fields"] is True
    assert body["is_signed"] is True
    assert body["info"] == {"title": "Example"}


def test_metadata_blank_pdf_reports_no_signature() -> None:
    client = TestClient(app)
    response = client.post(
        "/metadata",
        files={"file": ("blank.pdf", _blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["has_text"] is False
    assert body["has_signature_fields"] is False
    assert body["is_signed"] is False
    assert body["is_encrypted"] is False


def test_metadata_rejects_non_pdf_upload() -> None:
    client = TestClient(app)
    response = client.post(
        "/metadata",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a PDF."


def test_metadata_extraction_failure_returns_500(monkeypatch) -> None:
    def fake_extract(_input_path: str, *, filename: str, file_size_bytes: int) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.metadata._extract_metadata", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/metadata",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Metadata extraction failed: boom"
