FROM python:3.10.14-slim

# Fix Debian 12 (Bookworm) to include non-free repositories
RUN sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources

# Install system dependencies and Intel Arc support
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    python3-pip python3-dev build-essential \
    # Intel Arc GPU support
    vainfo intel-gpu-tools \
    intel-media-va-driver-non-free \
    onevpl-tools libvpl2 libvpl-dev \
    # FFmpeg with proper Intel support
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p /app/assets/temp /app/results && chmod -R 777 /app/assets /app/results

# Set Intel Arc environment variables for FFmpeg hardware acceleration
ENV LIBVA_DRIVER_NAME=iHD \
    LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri \
    INTEL_MEDIA_RUNTIME=/usr/lib/x86_64-linux-gnu/dri

EXPOSE 5000
CMD ["python3", "api.py"]
