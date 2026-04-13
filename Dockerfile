# syntax=docker/dockerfile:1

# ---- Stage 1: build widget ----
FROM node:20-slim AS widget-build
WORKDIR /build
COPY frontend/widget/package.json frontend/widget/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/widget/ .
RUN npm run build

# ---- Stage 2: runtime ----
FROM python:3.9-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --shell /bin/bash appuser

COPY app /app/app
COPY --from=widget-build /build/dist /app/frontend/widget/dist

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
