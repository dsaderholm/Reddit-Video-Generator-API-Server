FROM python:3.10.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

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

CMD ["python3", "api.py"]