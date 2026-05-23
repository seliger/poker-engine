FROM python:3.11-slim

LABEL maintainer="Poker Engine: Home Game Edition"
LABEL description="Local poker practice and home game engine"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

RUN mkdir -p /config /data

EXPOSE 5000

ENV POKER_ENV=container
ENV POKER_HOST=0.0.0.0
ENV POKER_PORT=5000
ENV POKER_CONFIG_PATH=/config/house_rules.json
ENV POKER_DB_PATH=/data/poker.db
ENV POKER_LOG_LEVEL=INFO

CMD ["python", "app.py"]
