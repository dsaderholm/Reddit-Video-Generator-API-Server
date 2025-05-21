FROM python:3.10.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-pip \
    ca-certificates \
    openssl \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Intel GPU drivers directly in container
RUN wget -qO - https://repositories.intel.com/graphics/intel-graphics.key | \
    gpg --dearmor --output /usr/share/keyrings/intel-graphics.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/graphics/ubuntu jammy arc" | \
    tee /etc/apt/sources.list.d/intel-gpu-jammy.list && \
    apt-get update && apt-get install -y \
    intel-media-va-driver-non-free \
    intel-opencl-icd \
    mesa-va-drivers \
    vainfo \
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

EXPOSE 5000

# Set environment variables for Intel GPU
ENV LIBVA_DRIVER_NAME=iHD
ENV LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri

CMD ["python3", "api.py"]