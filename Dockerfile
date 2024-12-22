FROM python:3.10.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p assets/temp results

EXPOSE 5000

CMD ["python3", "api.py"]