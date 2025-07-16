FROM python:3.9-slim

# System dependencies install karein
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    iproute2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Working directory set karein
WORKDIR /app

# Requirements copy karein aur install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code copy karein
COPY . .

# Required directories create karein
RUN mkdir -p downloads temp

# Port expose karein
EXPOSE 8080

# Start command
CMD ["bash", "start.sh"]
