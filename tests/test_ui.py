import re

from fastapi.testclient import TestClient

from app.main import app

_EXPECTED_OCR_PARAMS = frozenset(
    {
        "deskew",
        "force_ocr",
        "rotate_pages",
        "skip_text",
        "clean",
    }
)


def test_demo_ui_index() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"Async PDF Toolkit" in response.content
    assert response.headers.get("cache-control") == "no-cache"
    assert "__UI_ASSET_V__" not in response.text
    assert re.search(r'/ui/app\.js\?v=\d+', response.text)
    assert re.search(r'/ui/styles\.css\?v=\d+', response.text)


def test_demo_ui_assets() -> None:
    client = TestClient(app)
    js = client.get("/ui/app.js")
    css = client.get("/ui/styles.css")
    assert js.status_code == 200
    assert css.status_code == 200
    assert "TOOLS" in js.text
    assert js.headers.get("cache-control") == "no-cache"
    assert css.headers.get("cache-control") == "no-cache"


def test_demo_ui_ocr_checkbox_params_are_wired() -> None:
    client = TestClient(app)
    html = client.get("/").text
    js = client.get("/ui/app.js").text

    params = set(re.findall(r'data-ocr-param="([a-z_]+)"', html))
    assert params == _EXPECTED_OCR_PARAMS
    assert "[data-ocr-param]" in js
    assert "dataset.ocrParam" in js
