FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    iproute2 \
    procps \
    sysvinit-utils \  # For sysctl support
    && rm -rf /var/lib/apt/lists/*

# Apply TCP buffer tuning
RUN echo "net.core.rmem_max=4194304" >> /etc/sysctl.conf && \
    echo "net.core.wmem_max=4194304" >> /etc/sysctl.conf

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (including start.sh)
COPY . .

# Create required directories with permissions
RUN mkdir -p downloads temp && \
    chmod 777 downloads temp

# Expose port
EXPOSE 8080

# Start via custom shell script (applies ulimit/sysctl)
CMD ["bash", "start.sh"]
