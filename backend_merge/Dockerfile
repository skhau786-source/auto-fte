FROM python:3.10-slim

WORKDIR /app

# System dependencies (psycopg2/postgres driver ke liye zaroori hain)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pehle requirements copy karo (Docker layer caching ke liye - isse rebuild fast hota hai)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ab poora app code copy karo
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
