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


def test_extract_text_join_pages_default(monkeypatch) -> None:
    def fake_extract(_input_path: str) -> list[str]:
        return ["Hello", "World"]

    monkeypatch.setattr("app.api.extract_text._extract_text_pages", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/extract-text",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Hello\nWorld"}


def test_extract_text_pages_json(monkeypatch) -> None:
    def fake_extract(_input_path: str) -> list[str]:
        return ["page one", "page two"]

    monkeypatch.setattr("app.api.extract_text._extract_text_pages", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/extract-text?join_pages=false",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"pages": ["page one", "page two"]}


def test_extract_text_blank_pdf_returns_empty() -> None:
    client = TestClient(app)
    response = client.post(
        "/extract-text",
        files={"file": ("blank.pdf", _blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "text" in body
    assert body["text"].strip() == ""


def test_extract_text_rejects_non_pdf_upload() -> None:
    client = TestClient(app)
    response = client.post(
        "/extract-text",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a PDF."
