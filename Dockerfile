FROM node:18-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GWENGIFT_ENVIRONMENT=production \
    GWENGIFT_DATABASE_URL=sqlite:////data/gwengift.db \
    GWENGIFT_MARKET_CACHE_PATH=/data/tg-gifts-cache.json \
    GWENGIFT_FRONTEND_DIST_PATH=/app/frontend/dist

WORKDIR /app/backend
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/app/ ./app/
COPY backend/migrations/ ./migrations/
RUN python -m pip install --no-cache-dir .

COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/gwengift-entrypoint
RUN chmod 0555 /usr/local/bin/gwengift-entrypoint \
    && useradd --create-home --uid 10001 gwengift \
    && mkdir -p /data \
    && chown gwengift:gwengift /data

USER gwengift
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
ENTRYPOINT ["/usr/local/bin/gwengift-entrypoint"]
