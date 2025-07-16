FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /bot

# Copy files
COPY . .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Run bot
CMD ["python", "main.py"]
