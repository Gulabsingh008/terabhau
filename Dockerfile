# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Set environment variables (can be overridden in deployment)
ENV API_ID=${API_ID}
ENV API_HASH=${API_HASH}
ENV BOT_TOKEN=${BOT_TOKEN}
ENV API_ENDPOINT=${API_ENDPOINT}
ENV PORT=${PORT:-8080}

# Start the bot
CMD ["python3", "bot.py"]
