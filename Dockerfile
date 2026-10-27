# SilverFile in a container: the same Python and libraries on every machine.
#
#   docker build -t silverfile .
#   docker run --rm silverfile                     # clean demo case, prints the route
#   docker run --rm silverfile pytest -q           # the full test suite
#   docker run --rm -p 8501:8501 silverfile streamlit run src/ui/taxpayer_chat.py
#                                                  # taxpayer chat page: http://localhost:8501
#
# Secrets are never baked in: pass them at run time with --env-file .env.
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

# Requirements first, so code changes do not reinstall every library.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=silverfile:silverfile . .
USER silverfile

EXPOSE 8501
CMD ["python", "-m", "scripts.run_scenarios", "clean"]
