import io

import pypdfium2 as pdfium
from fastapi.testclient import TestClient

from app.main import app


def _one_page_pdf_bytes() -> bytes:
    doc = pdfium.PdfDocument.new()
    try:
        doc.new_page(200, 200)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    finally:
        doc.close()


def test_merge_endpoint_merges_two_pdfs() -> None:
    pdf_a = _one_page_pdf_bytes()
    pdf_b = _one_page_pdf_bytes()

    client = TestClient(app)
    response = client.post(
        "/merge",
        files=[
            ("files", ("a.pdf", pdf_a, "application/pdf")),
            ("files", ("b.pdf", pdf_b, "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")

    merged = pdfium.PdfDocument(response.content)
    try:
        assert len(merged) == 2
    finally:
        merged.close()


def test_merge_endpoint_rejects_non_pdf_upload() -> None:
    client = TestClient(app)
    response = client.post(
        "/merge",
        files=[
            ("files", ("a.pdf", _one_page_pdf_bytes(), "application/pdf")),
            ("files", ("note.txt", b"not a pdf", "text/plain")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a PDF."


def test_merge_endpoint_rejects_single_file() -> None:
    client = TestClient(app)
    response = client.post(
        "/merge",
        files=[
            ("files", ("a.pdf", _one_page_pdf_bytes(), "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "At least two PDF files are required."
