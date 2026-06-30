FROM python:3.11-slim

WORKDIR /app

# Tizim kutubxonalari (agar kerak bo'lsa kengaytirish mumkin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Sozlamalar/tarix saqlanadigan papka (docker-compose orqali mount qilinadi)
RUN mkdir -p /app/data

CMD ["python", "bot.py"]

