# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH

COPY backend/requirements.lock .
# Install the full hash-locked set, then drop CI/dev tooling (+transitive-only) from the runtime image.
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip uninstall -y \
        pytest pytest-asyncio pytest-cov coverage \
        ruff mypy mypy-extensions pathspec librt \
        iniconfig pluggy pygments

FROM python:3.12-slim

WORKDIR /app/backend

# curl: compose healthcheck; nodejs/npm: stdio MCP servers via npx.
# Note: Playwright also needs browser binaries/OS libs — not installed here.
# playwright stays startup_connect=false so container boot does not require browsers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /venv /venv
ENV PATH=/venv/bin:$PATH

COPY backend/ .

ENV PYTHONPATH=/app/backend
ENV DATA_DIR=/app/backend/data

RUN useradd -m -u 1000 par && chown -R par:par /app/backend
USER par

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
