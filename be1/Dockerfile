# syntax=docker/dockerfile:1
# ---- Backend image: FastAPI (DMX Advisor BE1) on Python 3.14 + uv ----
# Build context is the REPO ROOT so the image mirrors the repo layout:
#   /app/be1/app/...        (code)
#   /app/be1/data/...       (be1-local data)
#   /app/data/ontology_data.json  (repo-root data, read via parents[2])
FROM python:3.14-slim

# uv (fast, reproducible installs from uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/be1/.venv/bin:$PATH"

# Native build deps for wheels (argon2, psycopg, asyncpg) + curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/be1

# Dependency layer — cached unless pyproject/uv.lock change
COPY be1/pyproject.toml be1/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Application source (be1) + repo-root data dir
COPY be1/ /app/be1/
COPY data/ /app/data/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8100
ENTRYPOINT ["/app/be1/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
