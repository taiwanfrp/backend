import tomllib
from pathlib import Path
from fastapi import FastAPI

ROOT_DIR = Path(__file__).parent.parent
TOML_PATH = ROOT_DIR / "pyproject.toml"

with open(TOML_PATH, "rb") as f:
    pyproject_data = tomllib.load(f).get("project", {})

app = FastAPI(
    title=pyproject_data.get("app_name", "FastAPI"),
    version=pyproject_data.get("version", "0.1.0"),
    description=pyproject_data.get("description", "")
)

@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "Hello, World!"}

@app.get("/items/{item_id}")
async def read_item(item_id: int) -> dict[str, str | int]:
    return {"item_id": item_id, "description": f"This is item {item_id}"}