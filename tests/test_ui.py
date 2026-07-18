from fastapi.testclient import TestClient

from app.main import app


def test_demo_ui_index() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"Async PDF Toolkit" in response.content


def test_demo_ui_assets() -> None:
    client = TestClient(app)
    js = client.get("/ui/app.js")
    css = client.get("/ui/styles.css")
    assert js.status_code == 200
    assert css.status_code == 200
    assert "TOOLS" in js.text
