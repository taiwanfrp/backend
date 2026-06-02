from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, World!"}

def test_read_item():
    item_id = 42
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200
    assert response.json() == {
        "item_id": item_id,
        "description": f"This is item {item_id}"
    }

def test_read_item_invalid_id():
    response = client.get("/items/not_an_int")
    assert response.status_code == 422  # Unprocessable Entity for invalid input