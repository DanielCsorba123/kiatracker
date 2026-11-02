# Runs on x86 and on a Raspberry Pi (arm64): docker build -t kiatracker .
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" \
    KIATRACKER_DATA_DIR=/data
VOLUME /data
ENTRYPOINT ["kiatracker"]
CMD ["stats"]
