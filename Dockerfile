FROM python:3.10.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-pip \
    ca-certificates \
    openssl \
    curl \
    gnupg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Intel GPU drivers and runtime requirements
RUN wget -qO - https://repositories.intel.com/graphics/intel-graphics.key | gpg --dearmor --output /usr/share/keyrings/intel-graphics.gpg
RUN echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/graphics/ubuntu jammy arc" | tee /etc/apt/sources.list.d/intel-gpu-jammy.list
RUN apt-get update && apt-get install -y \
    intel-media-va-driver-non-free \
    intel-opencl-icd \
    intel-level-zero-gpu \
    level-zero \
    level-zero-dev \
    && rm -rf /var/lib/apt/lists/*

# Update CA certificates
RUN update-ca-certificates

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Intel PyTorch Extensions
RUN pip install --no-cache-dir intel-extension-for-pytorch oneccl_bind_pt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p /app/assets/temp /app/results

# Make sure the application can write to these directories
RUN chmod -R 777 /app/assets /app/results

EXPOSE 5000

CMD ["python3", "api.py"]
