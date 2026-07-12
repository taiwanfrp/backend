import tomllib
from pathlib import Path
from fastapi import FastAPI

from app.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

ROOT_DIR = Path(__file__).parent.parent
TOML_PATH = ROOT_DIR / "pyproject.toml"

with open(TOML_PATH, "rb") as f:
    pyproject_data = tomllib.load(f).get("project", {})

app = FastAPI(
    title=pyproject_data.get("app_name", "FastAPI"),
    version=pyproject_data.get("version", "0.1.0"),
    description=pyproject_data.get("description", "")
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

from app.middlewares.request_timer import RequestTimerMiddleware    # noqa: E402
app.add_middleware(RequestTimerMiddleware)

@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "Hello, World!"}

@app.get("/items/{item_id}")
async def read_item(item_id: int) -> dict[str, str | int]:
    return {"item_id": item_id, "description": f"This is item {item_id}"}

from app.exception_handlers import AuthException, auth_exception_handler    # noqa: E402
app.add_exception_handler(AuthException, auth_exception_handler)    # type: ignore[arg-type]

from app.routers import auth, users, system, nodes  # noqa: E402
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(system.router)
app.include_router(nodes.router)