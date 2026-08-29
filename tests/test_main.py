from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_favicon_redirect():
    response = client.get("/favicon.ico", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://taiwanfrp.me/favicon.ico"
