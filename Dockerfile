FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Download nltk files
COPY scripts/setup_nltk.py .
RUN python setup_nltk.py

# Install the embedding model
COPY scripts/download_embedder.py .
RUN python download_embedder.py

COPY app ./app

EXPOSE 8000 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
