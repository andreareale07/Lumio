FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Il servizio `worker` nel compose sovrascrive questo comando (nessuna migration lì:
# solo `app` applica lo schema all'avvio, per evitare migration concorrenti).
# `--forwarded-allow-ips`: uvicorn legge l'IP del client da X-Forwarded-For solo
# se la richiesta arriva dalle reti private dei container (l'nginx del frontend
# imposta l'header con l'IP reale); da un altro indirizzo l'header e' ignorato.
# Serve al rate limit per IP e all'IP inoltrato alla banca.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1'"]
