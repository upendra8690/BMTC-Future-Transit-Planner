# Planner web service: the API and the dashboard, served by uvicorn.
# Built and started by docker compose (see docker-compose.yml and docs/DEPLOY.md).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime packages. The constraints file pins each one to the version verified in docs/TEST_RESULTS.md.
COPY requirements.txt requirements-verified.txt ./
RUN pip install -r requirements.txt -c requirements-verified.txt

# The application lays out its paths from the project root, so these folders keep their names under /app.
COPY backend ./backend
COPY dashboard ./dashboard
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

# The service runs as an unprivileged user. Only the data folder (database and backups) is writable.
RUN groupadd --system --gid 10001 planner \
    && useradd --system --uid 10001 --gid planner --home-dir /app --shell /usr/sbin/nologin planner \
    && mkdir -p /app/data/backups \
    && chown -R planner:planner /app/data

ENV DATABASE_URL=sqlite:////app/data/planner.db \
    BACKUP_DIR=/app/data/backups \
    FORWARDED_ALLOW_IPS=127.0.0.1

USER planner
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# exec makes uvicorn the main process, so it receives the stop signal directly. --proxy-headers takes the client
# address from X-Forwarded-For only when the connection comes from one of the FORWARDED_ALLOW_IPS addresses.
# scripts/container_start.sh starts uvicorn; on Render it also loads the demo feed and trusts Render's proxy.
CMD ["sh", "scripts/container_start.sh"]
