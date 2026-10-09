FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 tesseract-ocr tesseract-ocr-eng tesseract-ocr-sqi \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m app && mkdir -p /app/storage && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS\" = \"1\" ]; then alembic upgrade head; fi && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
