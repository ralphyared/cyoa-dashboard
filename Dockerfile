# syntax=docker/dockerfile:1

# --- build the web app ---------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- python runtime ------------------------------------------------------------
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY engine/pyproject.toml engine/pyproject.toml
COPY server/pyproject.toml server/pyproject.toml
COPY engine/src engine/src
COPY server/src server/src
RUN uv sync --frozen --no-dev && rm /usr/local/bin/uv
COPY --from=web /web/dist /app/web/dist

ENV PATH=/app/.venv/bin:$PATH \
    HOME=/tmp \
    CYOA_DATA_DIR=/data \
    CYOA_STATIC_DIR=/app/web/dist \
    CYOA_PORT=8000
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["python", "-m", "cyoa_server"]
