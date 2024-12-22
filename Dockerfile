FROM python:3.10.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-pip \
    ca-certificates \
    openssl \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Update CA certificates
RUN update-ca-certificates

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p /app/assets/temp /app/results

# Make sure the application can write to these directories
RUN chmod -R 777 /app/assets /app/results

# Verify DNS resolution
RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf

EXPOSE 5000

CMD ["python3", "api.py"]
