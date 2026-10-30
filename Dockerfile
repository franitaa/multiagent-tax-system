# SilverFile in a container: the same Python and libraries on every machine.
#
#   docker build -t silverfile .
#   docker run --rm silverfile                     # clean demo case, prints the route
#   docker run --rm silverfile pytest -q           # the full test suite
#   docker compose up --build                      # the whole app, saved cases kept (docker-compose.yml)
#
# Saved cases (runtime/) and traces plus the audit log (traces/) belong in volumes, so they survive a
# new container: -v silverfile-runtime:/app/runtime -v silverfile-traces:/app/traces
# Secrets are never baked in. The W-2 page reads the .env file itself (not environment variables),
# so mount it: -v "$PWD/.env:/app/.env:ro"
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Run as an unprivileged user, not root.
RUN useradd --create-home --uid 1000 silverfile
WORKDIR /app
RUN chown silverfile:silverfile /app

# Requirements first, so code changes do not reinstall every library.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=silverfile:silverfile . .
USER silverfile
# Create the folders the volumes are mounted on, as the app user: a new Docker volume copies the
# owner of the folder it is mounted on, so without this it belongs to root and saving a case fails.
RUN mkdir -p runtime traces/audit

EXPOSE 8501
CMD ["python", "-m", "scripts.run_scenarios", "clean"]
