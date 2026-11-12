FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY src ./src
RUN uv sync --locked
ARG APP_VERSION=dev
ENV PATH=/app/.venv/bin:$PATH APP_VERSION=${APP_VERSION} PORT=8084
RUN useradd --create-home app
USER app
CMD ["sh", "-c", "exec uvicorn engine.main:app --host 0.0.0.0 --port ${PORT}"]
