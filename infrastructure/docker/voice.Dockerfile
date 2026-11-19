# Voice engine image: the LiveKit Agents worker running the AI Speaking examiner (Gemini Live).
# Build context: repository root (the uv workspace lockfile lives there).

FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.14.5-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY ai-engine/pyproject.toml ai-engine/pyproject.toml
COPY voice-engine/pyproject.toml voice-engine/pyproject.toml
RUN uv sync --frozen --no-dev --package ielts-voice --no-install-workspace

COPY ai-engine/ ai-engine/
COPY voice-engine/ voice-engine/
RUN uv sync --frozen --no-dev --package ielts-voice --no-editable

FROM python:3.14.5-slim-trixie AS runtime
RUN groupadd --system app \
    && useradd --system --gid app --create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
WORKDIR /home/app
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER app
# `start` = production mode (no file watching). Needs LIVEKIT_*, GEMINI_API_KEY,
# BACKEND_INTERNAL_URL and SPEAKING_EVENTS_TOKEN.
CMD ["python", "-m", "ielts_voice.agent", "start"]
