from fastapi.testclient import TestClient

from app.main import app


def test_ocr_endpoint_returns_pdf(monkeypatch) -> None:
    def fake_run_ocr(input_path: str, output_path: str, **_: object) -> None:
        with open(input_path, "rb") as src, open(output_path, "wb") as dst:
            dst.write(src.read())

    monkeypatch.setattr("app.api.ocr._run_ocr", fake_run_ocr)

    client = TestClient(app)
    pdf_bytes = b"%PDF-1.4\n%mock\n"
    response = client.post(
        "/ocr",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == pdf_bytes


def test_ocr_endpoint_rejects_non_pdf_upload() -> None:
    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a PDF."


def test_ocr_endpoint_passes_query_parameters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_ocr(
        input_path: str,
        output_path: str,
        *,
        language: str | None,
        deskew: bool,
        force_ocr: bool,
        optimize: int | None,
        rotate_pages: bool,
        skip_text: bool,
        clean: bool,
        remove_background: bool,
    ) -> None:
        captured.update(
            {
                "language": language,
                "deskew": deskew,
                "force_ocr": force_ocr,
                "optimize": optimize,
                "rotate_pages": rotate_pages,
                "skip_text": skip_text,
                "clean": clean,
                "remove_background": remove_background,
            }
        )
        with open(output_path, "wb") as dst:
            dst.write(b"%PDF-1.4\n")

    monkeypatch.setattr("app.api.ocr._run_ocr", fake_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr?language=eng&deskew=true&force_ocr=true&optimize=2"
        "&rotate_pages=true&skip_text=false&clean=true&remove_background=false",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 200
    assert captured == {
        "language": "eng",
        "deskew": True,
        "force_ocr": True,
        "optimize": 2,
        "rotate_pages": True,
        "skip_text": False,
        "clean": True,
        "remove_background": False,
    }


def test_ocr_endpoint_returns_500_on_ocr_failure(monkeypatch) -> None:
    def failing_run_ocr(input_path: str, output_path: str, **_: object) -> None:
        raise RuntimeError("ocr failed")

    monkeypatch.setattr("app.api.ocr._run_ocr", failing_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 500
    assert "OCR processing failed: ocr failed" in response.json()["detail"]
