FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p downloads temp && \
    chmod -R 777 downloads temp

# Expose ports
EXPOSE 8080 6800

# Start command
CMD ["bash", "start.sh"]
