FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /code

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Dependencies Cache
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

COPY . /code

ENV PATH="/code/.venv/bin:$PATH"

EXPOSE 8000

CMD ["fastapi", "run", "--host", "0.0.0.0", "--port", "8000"]