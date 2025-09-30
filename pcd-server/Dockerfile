FROM python:3.11-slim-bookworm

# System deps for Open3D (headless)
RUN apt-get update && apt-get install -y \
    libgl1 libglx-mesa0 libegl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pcd-server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pcd-server /app

ENV PYTHONUNBUFFERED=1 \
    SQLITE_PATH=/data/pcd.sqlite3 \
    MINIO_ENDPOINT=minio:9000 \
    MINIO_ROOT_USER=minioadmin \
    MINIO_ROOT_PASSWORD=minioadmin \
    MINIO_BUCKET=pcd \
    MINIO_SECURE=0

VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


