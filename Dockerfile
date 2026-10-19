# syntax=docker/dockerfile:1
# Stage 1: build the React app
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime serving the API and the built frontend on one port
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Layout must match the repo: config.py resolves the repo root as parents[2] of backend/app/config.py
COPY backend/app backend/app
COPY backend/samples backend/samples
COPY backend/precomputed backend/precomputed
COPY --from=web /web/dist frontend/dist

# Run as a non-root user; .cache is the disk cache (Qloo responses and saved plans)
RUN useradd --create-home --uid 10001 app && mkdir -p /app/.cache && chown -R app:app /app/.cache
USER app

WORKDIR /app/backend
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"

# One worker: the per-IP rate limiter lives in memory. Platforms like Render inject $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
