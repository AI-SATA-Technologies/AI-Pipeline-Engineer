# School Face Attendance API
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_DIR=/models

WORKDIR /app

# OpenCV runtime needs libGL + glib (not in slim by default).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Models are NOT baked into the image. Provide them at runtime by either:
#   - mounting a host directory:   -v /path/to/models:/models
#   - or running once in-container: python download_models.py
# Supply DB / LMS / security config via -e VARS or --env-file.
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
