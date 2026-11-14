FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data DEMO_DIR=/demo EMBED_WORKER=false
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
ARG INSTALL_XIAOMI_OCR=false
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY requirements-xiaomi-ocr.txt ./
RUN if [ "$INSTALL_XIAOMI_OCR" = "true" ]; then \
    pip install --no-cache-dir torch==2.14.0 torchvision==0.29.0 --index-url "$PYTORCH_INDEX_URL" -c constraints.txt && \
    pip install --no-cache-dir -r requirements-xiaomi-ocr.txt -c constraints.txt; fi
COPY app/ app/
COPY demo/manifest.json demo/manifest.json
COPY demo/expected.json demo/expected.json
COPY task/data/ /demo/
COPY cases/catalog.json cases/catalog.json
COPY cases/generated/ cases/generated/
COPY --from=frontend /ui/dist/ frontend/dist/
RUN useradd --uid 10001 --create-home audit && mkdir -p /data && chown audit:audit /data
USER audit
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
