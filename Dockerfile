# Build stage
FROM ubuntu:22.04 as builder

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    cmake \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone and build whisper.cpp
RUN git clone https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    make

# Runtime stage
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy whisper.cpp from builder
COPY --from=builder /build/whisper.cpp /app/whisper.cpp
COPY --from=builder /build/whisper.cpp/models/download-ggml-model.sh /app/download-ggml-model.sh
RUN chmod +x /app/download-ggml-model.sh

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY config.py .
COPY celery_app.py .
COPY celery_worker.py .

# Create models directory
RUN mkdir -p models

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["python3", "app.py"]
