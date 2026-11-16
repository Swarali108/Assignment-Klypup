# AURELIA API + pipeline + discovery (FastAPI on uvicorn). Railway builds this file from the repo root.
# Local check:  docker build -t aurelia-api . && docker run --rm -p 8130:8000 -e SESSION_SECRET=... aurelia-api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# A fixed non-root user. On Railway a mounted volume is owned by root: set RAILWAY_RUN_UID=0 there (see docs/DEPLOYMENT.md).
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

# Every version pinned (the full set the image was verified with).
COPY requirements-deploy.txt ./
RUN pip install -r requirements-deploy.txt

COPY --chown=app:app . .
# /app must be writable by the app user: DATA_DIR mode replaces outputs/, events/, cache/, api/state with symlinks.
RUN mkdir -p api/state cache/fetch cache/pages && chown app:app /app /app/api/state /app/cache /app/cache/fetch /app/cache/pages

USER app
EXPOSE 8000

# python -m api: seeds/links DATA_DIR when set, then one uvicorn process on $HOST:$PORT (Railway injects PORT).
CMD ["python", "-m", "api"]
