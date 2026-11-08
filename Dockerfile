# syntax=docker/dockerfile:1
# One image for the collector and the dashboard; runs on x86 and on a Raspberry Pi (arm64).
#   docker compose up -d dashboard      -> http://127.0.0.1:8501 (your data, this computer only)
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=2

# Dependencies first, so code changes don't reinstall them
COPY pyproject.toml uv.lock ./
# The cache mount keeps downloaded wheels between builds, so a flaky connection resumes instead of restarting
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra dashboard --no-install-project
COPY README.md ./
COPY src ./src
COPY .streamlit ./.streamlit
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra dashboard

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    KIATRACKER_DATA_DIR=/data
VOLUME /data
EXPOSE 8501
ENTRYPOINT ["kiatracker"]
CMD ["stats"]
