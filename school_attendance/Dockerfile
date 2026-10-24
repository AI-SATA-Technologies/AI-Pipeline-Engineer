# School Face Attendance API
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODEL_DIR=/models

WORKDIR /app

# The server needs no GUI, so use the headless OpenCV build (no libGL/X11);
# only glib is still required at runtime. The GUI build stays in
# requirements.txt for viewer.py on desktop machines.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN sed 's/^opencv-python==/opencv-python-headless==/' requirements.txt > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY . .

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /models && chown app /models
USER app

# Models are NOT baked into the image. Provide them at runtime by either:
#   - mounting a host directory:   -v /path/to/models:/models:ro
#   - or running once in-container: python download_models.py   (SHA-256 verified)
# Supply DB / LMS / security / camera config via -e VARS or --env-file.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

# Exactly ONE worker: attendance state (pending cache, outbox, camera) lives in
# this process's memory. More workers would each load their own copy.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
