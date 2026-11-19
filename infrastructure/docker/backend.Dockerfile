# Backend image (API now; Celery workers later run the same image with a different command, ADR-002).
# Build context: repository root (the uv workspace lockfile lives there).

FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.14.5-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# 1) Third-party dependencies only (cached until the lockfile changes).
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY ai-engine/pyproject.toml ai-engine/pyproject.toml
COPY voice-engine/pyproject.toml voice-engine/pyproject.toml
RUN uv sync --frozen --no-dev --package ielts-backend --no-install-workspace

# 2) The backend package itself, installed non-editable so the runtime needs no source tree.
COPY backend/ backend/
COPY ai-engine/ ai-engine/
RUN uv sync --frozen --no-dev --package ielts-backend --no-editable

FROM python:3.14.5-slim-trixie AS runtime
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
# Alembic config + migration scripts for the one-off `migrate` job (same image, different command).
WORKDIR /app
COPY --from=build /src/backend/alembic.ini /app/alembic.ini
COPY --from=build /src/backend/migrations /app/migrations
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
