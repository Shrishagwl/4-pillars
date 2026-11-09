# FastAPI service template (Python)

Starting point for every Python service. Copy this folder, rename `src/service_template`,
then update `SERVICE_NAME` / `DEFAULT_PORT` in `config.py`, the package name in `pyproject.toml`,
and the module path in the Dockerfile `CMD`.

What you get: FastAPI + Pydantic, `GET /health`, settings from env vars (pydantic-settings),
JSON logs with Cloud Logging `severity`, pytest with `TestClient`, ruff, and a uv-based Dockerfile.

    uv sync
    uv run pytest
    uv run ruff check .
    uv run uvicorn service_template.main:app --reload --port 8080
    docker build -t service-template .
