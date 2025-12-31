# Whisper.cpp REST API

A Docker-based REST API for OpenAI's Whisper speech-to-text model using [whisper.cpp](https://github.com/ggerganov/whisper.cpp) for efficient inference.

## Features

- 🎤 REST API for audio transcription
- 🐳 Docker support with docker-compose
- 📊 Multiple model support (tiny, base, small, medium, large)
- 🌍 Multi-language support
- 📈 Fast CPU inference with whisper.cpp
- 🔄 Model management (list, download)
- 📝 JSON output with segment details
- 🏥 Health checks and monitoring

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 4GB+ RAM (recommended for base model)
- 10GB+ storage (for models)

### Using Docker Compose

1. **Clone and navigate to the repository:**

```bash
cd whisper-api
```

2. **Start the service:**

```bash
docker-compose up -d
```

3. **Check health:**

```bash
curl http://localhost:8000/health
```

4. **List available models:**

```bash
curl http://localhost:8000/api/v1/models
```

### Usage Examples

#### Transcribe Audio

```bash
curl -X POST http://localhost:8000/api/v1/transcribe \
  -F "file=@audio.mp3" \
  -F "model=base.en" \
  -F "language=en"
```

#### Download a Model

```bash
curl -X POST http://localhost:8000/api/v1/download-model/base.en
```

#### Get API Info

```bash
curl http://localhost:8000/api/v1/info
```

## API Endpoints

### `GET /health`

Health check endpoint.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00.000000",
  "service": "whisper-api"
}
```

### `GET /api/v1/models`

List available Whisper models.

**Response:**

```json
{
  "status": "success",
  "models": ["base.en", "small.en", "medium.en"],
  "count": 3
}
```

### `POST /api/v1/transcribe`

Transcribe audio file.

**Parameters:**

- `file` (required): Audio file (multipart/form-data)
- `model` (optional): Model name (default: base.en)
- `language` (optional): Language code (e.g., en, es, fr)

**Supported audio formats:** mp3, wav, m4a, flac, ogg, wma, aac, webm

**Response:**

```json
{
  "status": "success",
  "text": "Full transcription text...",
  "segments": [
    {
      "id": 0,
      "seek": 0,
      "start": 0.0,
      "end": 3.2,
      "text": "Segment text",
      "tokens": [...]
    }
  ],
  "model": "base.en",
  "language": "en"
}
```

### `POST /api/v1/download-model/<model_name>`

Download a specific Whisper model.

**Models available:**

- tiny, tiny.en
- base, base.en
- small, small.en
- medium, medium.en
- large

**Response:**

```json
{
  "status": "success",
  "message": "Model base.en downloaded successfully"
}
```

### `GET /api/v1/info`

Get API and system information.

**Response:**

```json
{
  "status": "success",
  "api_version": "1.0.0",
  "service": "Whisper.cpp API",
  "timestamp": "2024-01-01T12:00:00.000000",
  "upload_path": "/app/uploads",
  "model_path": "/app/models",
  "threads": 4
}
```

## Configuration

### Environment Variables

Create a `.env` file or edit `docker-compose.yml`:

```bash
# Server
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your-secret-key

# Paths
MODEL_PATH=/app/models
UPLOAD_PATH=/app/uploads

# Performance
THREADS=4

# Logging
LOG_LEVEL=INFO
DEBUG=False
```

### Docker Compose Configuration

Edit `docker-compose.yml` to customize:

- Port mappings
- Volume mounts
- Resource limits
- Environment variables

## Model Information

| Model  | Size  | Speed     | Accuracy  |
| ------ | ----- | --------- | --------- |
| tiny   | 75M   | Very fast | Lower     |
| base   | 140M  | Fast      | Good      |
| small  | 461M  | Medium    | Better    |
| medium | 1.5GB | Slower    | Excellent |
| large  | 2.9GB | Slowest   | Best      |

Add `.en` suffix for English-only models (faster).

## File Size Limits

- Max upload: 500MB (configurable in config.py)
- Recommended max: 200MB for better performance

## Performance Tips

1. **Use English-only models** (e.g., `base.en`) if only transcribing English
2. **Adjust THREADS** based on CPU cores (default: 4)
3. **Pre-download models** to avoid download delays on first request
4. **Use smaller models** (tiny, base) for faster inference
5. **Keep models in dedicated volume** for persistence

## Building Locally

```bash
# Build image
docker build -t whisper-api:latest .

# Run container
docker run -p 8000:8000 \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/uploads:/app/uploads \
  whisper-api:latest
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs whisper-api

# Rebuild image
docker-compose build --no-cache
```

### Out of memory

- Use smaller model (tiny or base)
- Increase host memory limit
- Reduce THREADS count

### Model download fails

```bash
# Check internet connection
# Manually download model:
docker exec whisper-api bash /app/whisper.cpp/models/download-ggml-model.sh base.en
```

### Slow transcription

- Use fewer threads
- Use smaller model
- Check CPU availability

## Stopping the Service

```bash
# Stop container
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Production Deployment

For production, consider:

1. Using a reverse proxy (nginx)
2. Adding authentication
3. Setting proper resource limits
4. Monitoring with Prometheus/Grafana
5. Using a dedicated GPU machine
6. Implementing request queuing

## Logs

```bash
# View logs
docker-compose logs -f whisper-api

# Clear logs
docker-compose logs --tail 0 whisper-api
```

## License

This API is built on top of [whisper.cpp](https://github.com/ggerganov/whisper.cpp).

See the respective projects for licensing information:

- [Whisper](https://github.com/openai/whisper) - MIT License
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) - MIT License
# whisper-api
