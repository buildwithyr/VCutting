# Backend: FastAPI mit OpenCascade (OCP), OpenCV und Matplotlib
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    VCUTTING_DATA_DIR=/data

# OCP und OpenCV brauchen einige Systembibliotheken. libgl1 und libglu1-mesa
# gehoeren zu VTK, das als Abhaengigkeit von cadquery-ocp mitkommt.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libgl1 \
        libglu1-mesa \
        libxrender1 \
        libxext6 \
        libsm6 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pyproject.toml ./

# Ohne Root laufen und ein beschreibbares Datenverzeichnis bereitstellen.
RUN useradd --create-home --uid 10001 vcutting \
    && mkdir -p /data \
    && chown -R vcutting:vcutting /data /app
USER vcutting

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
