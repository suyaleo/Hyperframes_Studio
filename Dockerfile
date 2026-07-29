FROM node:22-bookworm-slim AS node-deps

WORKDIR /build/remotion-template
COPY remotion-template/package.json remotion-template/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
RUN npm install --prefix /opt/hyperframes --ignore-scripts --no-audit --no-fund hyperframes@0.7.78

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy AS runtime

ARG VERSION=0.1.0
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Hyperframes Studio" \
      org.opencontainers.image.description="Evidence-first AI studio for Hyperframes HTML cards and Remotion video" \
      org.opencontainers.image.source="https://github.com/suyaleo/Hyperframes_Studio" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PRODUCER_LOW_MEMORY_MODE=1 \
    HYPERFRAMES_EXTRACT_CACHE_DIR=/tmp/hyperframes-extract-cache \
    HYPERFRAMES_DATA_DIR=/data \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON=3.12

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl ffmpeg gnupg tini \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --from=node-deps /build/remotion-template/node_modules /app/remotion-template/node_modules
COPY --from=node-deps /opt/hyperframes /opt/hyperframes
COPY . .

ENV PATH="/app/.venv/bin:/opt/hyperframes/node_modules/.bin:${PATH}" \
    HYPERFRAMES_BROWSER_PATH=/ms-playwright/chromium_headless_shell-1148/chrome-linux/headless_shell

RUN useradd --create-home --uid 10001 appuser \
  && mkdir -p /data/output /data/research /data/compositions/projects /data/compositions/remotion \
  && chown -R appuser:appuser /app /data /home/appuser

USER appuser

EXPOSE 8770
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8770/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8770"]
