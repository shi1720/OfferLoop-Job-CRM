# ---------------------------------------------------------------------------
# OfferLoop — single-container build for Cloud Run.
# Stage 1 compiles the React frontend; stage 2 is a slim Python runtime that
# serves both the API and the static bundle. One service, scales to zero.
# ---------------------------------------------------------------------------

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OFFERLOOP_STATIC_DIR=/app/static \
    OFFERLOOP_DATA_DIR=/app/data

COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend && rm -rf /root/.cache

COPY data/ /app/data/
COPY --from=frontend /build/dist /app/static

RUN useradd --create-home offerloop
USER offerloop

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT:-8080}"]
