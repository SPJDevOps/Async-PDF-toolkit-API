import io

import pypdfium2 as pdfium
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def _pdf_bytes(*, pages: int = 1, width: float = 200, height: float = 200) -> bytes:
    doc = pdfium.PdfDocument.new()
    try:
        for _ in range(pages):
            doc.new_page(width, height)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    finally:
        doc.close()


def test_to_image_endpoint_returns_png() -> None:
    client = TestClient(app)
    response = client.post(
        "/to-image",
        files={"file": ("sample.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG")


def test_to_image_endpoint_page_param() -> None:
    client = TestClient(app)
    pdf = _pdf_bytes(pages=2)

    ok = client.post(
        "/to-image?page=2",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
    )
    assert ok.status_code == 200
    assert ok.content.startswith(b"\x89PNG")

    bad = client.post(
        "/to-image?page=3",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
    )
    assert bad.status_code == 400
    assert "out of range" in bad.json()["detail"]


def test_to_image_endpoint_dpi_affects_size() -> None:
    client = TestClient(app)
    pdf = _pdf_bytes(width=72, height=72)  # 1 inch square

    low = client.post(
        "/to-image?dpi=72",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
    )
    high = client.post(
        "/to-image?dpi=300",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
    )

    assert low.status_code == 200
    assert high.status_code == 200

    low_img = Image.open(io.BytesIO(low.content))
    high_img = Image.open(io.BytesIO(high.content))
    assert high_img.width > low_img.width
    assert high_img.height > low_img.height


def test_to_image_endpoint_rejects_non_pdf_upload() -> None:
    client = TestClient(app)
    response = client.post(
        "/to-image",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a PDF."


def test_to_image_endpoint_returns_400_when_pdf_has_no_pages(monkeypatch) -> None:
    from app.api.to_image import _EmptyPdfError

    def empty_pdf(*_args: object, **_kwargs: object) -> None:
        raise _EmptyPdfError()

    monkeypatch.setattr("app.api.to_image._render_page_to_png", empty_pdf)

    client = TestClient(app)
    response = client.post(
        "/to-image",
        files={"file": ("empty.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "PDF has no pages."


def test_to_image_endpoint_returns_500_on_render_failure(monkeypatch) -> None:
    def failing_render(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("render failed")

    monkeypatch.setattr("app.api.to_image._render_page_to_png", failing_render)

    client = TestClient(app)
    response = client.post(
        "/to-image",
        files={"file": ("sample.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 500
    assert "PDF to image failed: render failed" in response.json()["detail"]
