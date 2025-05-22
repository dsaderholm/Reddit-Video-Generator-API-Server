FROM python:3.10.14-slim

# Install Intel Arc-optimized packages and system dependencies
RUN apt-get update && apt-get install -y \
    # Essential tools
    wget \
    curl \
    gnupg \
    software-properties-common \
    ca-certificates \
    # Intel GPU and media packages
    intel-media-va-driver-non-free \
    intel-gpu-tools \
    libva-utils \
    vainfo \
    # FFmpeg and media libraries
    ffmpeg \
    # Build tools for Python packages
    python3-pip \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Add Intel APT repository for OneAPI runtime
RUN wget -qO - https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | apt-key add - && \
    echo "deb https://apt.repos.intel.com/oneapi all main" | tee /etc/apt/sources.list.d/oneAPI.list

# Install Intel OneAPI components for optimal Arc support
RUN apt-get update && apt-get install -y \
    intel-oneapi-runtime-libs \
    intel-level-zero-gpu \
    level-zero \
    && rm -rf /var/lib/apt/lists/*

# Update CA certificates
RUN update-ca-certificates

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install PyTorch with Intel Extension for Arc GPU support first
RUN pip install --no-cache-dir torch==2.3.1

# Install Intel Extension for PyTorch for Arc GPU
RUN pip install --no-cache-dir intel-extension-for-pytorch==2.3.110+xpu \
    --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/

# Install the rest of the requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/assets/temp /app/results && \
    chmod -R 777 /app/assets /app/results

# Set Intel Arc optimization environment variables
ENV ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
    INTEL_DEVICE_TYPE=gpu \
    USE_IPEX=1 \
    LIBVA_DRIVER_NAME=iHD \
    LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri \
    INTEL_MEDIA_RUNTIME=/usr/lib/x86_64-linux-gnu/dri \
    INTEL_GPU_MIN_FREQ=0 \
    INTEL_GPU_MAX_FREQ=2100 \
    ZE_AFFINITY_MASK=0 \
    MFX_IMPL_BASEDIR=/usr/lib/x86_64-linux-gnu

# Create a script to verify Intel Arc GPU setup
RUN echo '#!/bin/bash\n\
echo "🔍 Verifying Intel Arc GPU setup..."\n\
echo "Hardware devices:"\n\
ls -la /dev/dri/ || echo "❌ No DRI devices found"\n\
echo "VA-API test:"\n\
vainfo --display drm --device /dev/dri/renderD128 2>/dev/null | head -10 || echo "⚠️ VA-API test failed"\n\
echo "FFmpeg QSV codecs:"\n\
ffmpeg -hide_banner -encoders 2>/dev/null | grep qsv || echo "⚠️ No QSV encoders found"\n\
echo "Python Intel XPU test:"\n\
python3 -c "import torch; import intel_extension_for_pytorch as ipex; print(f\\"PyTorch: {torch.__version__}\\"); print(f\\"IPEX: {ipex.__version__}\\"); print(f\\"XPU available: {torch.xpu.is_available()}\\");" || echo "⚠️ Intel XPU test failed"\n\
echo "✅ Setup verification complete"\n\
' > /app/verify_intel_arc.sh && chmod +x /app/verify_intel_arc.sh

EXPOSE 5000

# Add healthcheck for Intel Arc GPU
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import torch; import intel_extension_for_pytorch as ipex; print('Intel Arc GPU healthy' if torch.xpu.is_available() else 'Intel Arc GPU not available')" || exit 1

CMD ["python3", "api.py"]
