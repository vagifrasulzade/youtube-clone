# syntax=docker/dockerfile:1
# One image for api, worker, beat and migrate (same code, same models).

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- production image ---
FROM base AS runtime
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=2)"]
# The API is reachable only through nginx on the internal network, so proxy headers are trusted.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]

# --- test image: runtime code + dev dependencies + tests ---
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests
USER app
CMD ["python", "-m", "pytest", "-q"]
