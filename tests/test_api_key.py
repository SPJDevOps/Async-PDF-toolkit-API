from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.main import app


def test_job_endpoint_open_when_api_key_unset(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "")
    clear_settings_cache()

    def fake_run_ocr(input_path: str, output_path: str, **_: object) -> None:
        with open(input_path, "rb") as src, open(output_path, "wb") as dst:
            dst.write(src.read())

    monkeypatch.setattr("app.api.ocr._run_ocr", fake_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 200


def test_job_endpoint_rejects_missing_api_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-demo-key")
    clear_settings_cache()

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key."


def test_job_endpoint_rejects_wrong_api_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-demo-key")
    clear_settings_cache()

    client = TestClient(app)
    response = client.post(
        "/ocr",
        headers={"X-API-Key": "wrong-key"},
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 401


def test_job_endpoint_accepts_correct_api_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-demo-key")
    clear_settings_cache()

    def fake_run_ocr(input_path: str, output_path: str, **_: object) -> None:
        with open(input_path, "rb") as src, open(output_path, "wb") as dst:
            dst.write(src.read())

    monkeypatch.setattr("app.api.ocr._run_ocr", fake_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr",
        headers={"X-API-Key": "secret-demo-key"},
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 200


def test_health_and_ui_remain_open_when_api_key_set(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-demo-key")
    clear_settings_cache()

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    ui = client.get("/")
    assert ui.status_code == 200
    assert "text/html" in ui.headers["content-type"]
