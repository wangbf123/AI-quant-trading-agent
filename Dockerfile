FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend-v2/package.json frontend-v2/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca --mount=type=cache,target=/root/.npm \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi && npm ci --no-audit --no-fund
COPY frontend-v2/ ./
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    AQR_DATA_DIR=/app/data/research \
    LOG_LLM_CHAT_CONTENT=false \
    MAX_RETRY=3 \
    RETRY_WAIT_SECONDS=2 \
    OMP_NUM_THREADS=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 git && rm -rf /var/lib/apt/lists/*
COPY . /app
COPY --from=frontend /web/dist /app/frontend-v2/dist
# Keep the large CPU/quant stack in the last filesystem layer. This also avoids
# repeated full layer copies on cloud Docker daemons using the vfs driver.
RUN --mount=type=secret,id=proxy_ca --mount=type=cache,target=/root/.cache/pip \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi && \
    pip install 'torch==2.6.0+cpu' --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements/research.lock && \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0 pip install --no-build-isolation --no-deps . && \
    useradd --create-home --uid 10001 research && mkdir -p /app/data && chown -R research:research /app
USER research
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "frontend-v2/backend/app.py"]
