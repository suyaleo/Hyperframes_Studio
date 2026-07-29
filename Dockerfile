FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gnupg ffmpeg unzip \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir playwright==1.49.1 \
  && playwright install chromium
# Prefetch Hyperframes CLI + managed Chrome for local renders
RUN npm install -g hyperframes@0.7.78 \
  && hyperframes browser ensure \
  && hyperframes doctor || true
COPY remotion-template/package.json remotion-template/package.json
RUN cd remotion-template && npm install --no-fund --no-audit   && npx remotion browser ensure || true
COPY . .
WORKDIR /app/api
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# N100-friendly Hyperframes profile
ENV PRODUCER_LOW_MEMORY_MODE=1
ENV HYPERFRAMES_EXTRACT_CACHE_DIR=/tmp/hyperframes-extract-cache
EXPOSE 8770
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8770"]
