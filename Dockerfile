FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /bot

# Copy files
COPY . .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for Render
EXPOSE 8080

# Run app
CMD ["python", "main.py"]
