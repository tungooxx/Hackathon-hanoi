# syntax=docker/dockerfile:1
# ---- Backend image: FastAPI (DMX Advisor BE1) on Python 3.14 + uv ----
FROM python:3.14-slim

# uv (fast, reproducible installs from uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Build/runtime deps for native wheels (argon2, psycopg, asyncpg) + curl for entrypoint waits
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer — cached unless pyproject/uv.lock change
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Application source
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8100
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
