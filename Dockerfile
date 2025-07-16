# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Environment variables
ENV API_ID=26494161
ENV API_HASH=55da841f877d16a3a806169f3c5153d3
ENV BOT_TOKEN=7758524025:AAEVf_OePVQ-6hhM1GfvRlqX3QZIqDOivtw
ENV API_ENDPOINT=http://zozo-api.onrender.com/download?url=
ENV PORT=8080

CMD ["python", "bot.py"]
