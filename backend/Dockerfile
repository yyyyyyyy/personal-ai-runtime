FROM python:3.12-slim

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.lock .
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY backend/ .

ENV PYTHONPATH=/app/backend
ENV DATA_DIR=/app/backend/data

RUN useradd -m -u 1000 par && chown -R par:par /app/backend
USER par

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
