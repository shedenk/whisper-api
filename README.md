# Whisper.cpp REST API

A Docker-based REST API for OpenAI's Whisper speech-to-text model using [whisper.cpp](https://github.com/ggerganov/whisper.cpp) for efficient inference.

## Features

- 🎤 REST API for audio transcription
- 🐳 Docker support with docker-compose
- ⚡ **Async processing with Redis + Celery** for long audio files
- 📊 Multiple model support (tiny, base, small, medium, large)
- 🌍 Multi-language support
- 📈 Fast CPU inference with whisper.cpp
- 🔄 Model management (list, download)
- 📝 JSON output with segment details
- 🏥 Health checks and monitoring
- 📊 Job queue & status tracking
- 🔀 Scalable worker architecture

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

#### Synchronous Transcription (Small files)

```bash
curl -X POST http://localhost:8000/api/v1/transcribe \
  -F "file=@audio.mp3" \
  -F "model=base.en" \
  -F "language=en"
```

#### Async Transcription (Large files, 1+ hour)

```bash
# Submit job
curl -X POST http://localhost:8000/api/v1/transcribe-async \
  -F "file=@long_audio.mp3" \
  -F "model=base.en"

# Response:
# {
#   "status": "submitted",
#   "job_id": "abc-123-def-456",
#   "poll_url": "/api/v1/job/abc-123-def-456"
# }

# Check status
curl http://localhost:8000/api/v1/job/abc-123-def-456

# Get result
curl http://localhost:8000/api/v1/result/abc-123-def-456

# List all jobs
curl http://localhost:8000/api/v1/jobs?status=completed

# Cancel job
curl -X DELETE http://localhost:8000/api/v1/job/abc-123-def-456
```

#### Download a Model

```bash
curl -X POST http://localhost:8000/api/v1/download-model/base.en
```

#### Get API Info

```bash
curl http://localhost:8000/api/v1/info
```

## Architecture

### Synchronous Mode

- Direct API request → Processing → Response
- Suitable for: Small files (<10min), immediate response needed
- Timeout: 10 minutes

### Async Mode (with Redis + Celery)

- API request → Queue → Worker processes → Polling for result
- Suitable for: Large files (>10min), batch processing, scalability
- Multiple workers can process jobs in parallel
- Job results cached in Redis for 24 hours

## API Endpoints

### Health & Info

#### `GET /health`

Health check endpoint.

#### `GET /api/v1/info`

Get API and system information.

### Synchronous Endpoints

#### `GET /api/v1/models`

List available Whisper models.

#### `POST /api/v1/transcribe`

Transcribe audio file synchronously.

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
      "text": "Segment text"
    }
  ],
  "model": "base.en",
  "language": "en"
}
```

### Async Endpoints

#### `POST /api/v1/transcribe-async`

Submit audio for async transcription.

**Parameters:** Same as `/api/v1/transcribe`

**Response (202 Accepted):**

```json
{
  "status": "submitted",
  "job_id": "uuid-string",
  "message": "Job submitted for processing",
  "poll_url": "/api/v1/job/uuid-string",
  "result_url": "/api/v1/result/uuid-string"
}
```

#### `GET /api/v1/job/{job_id}`

Get transcription job status.

**Response:**

```json
{
  "status": "queued|processing|completed|failed",
  "job_id": "uuid-string",
  "celery_status": "PENDING|PROCESSING|SUCCESS|FAILURE",
  "progress": 0-100,
  "message": "Status message",
  "model": "base.en",
  "submitted_at": "2024-01-01T12:00:00"
}
```

#### `GET /api/v1/result/{job_id}`

Get transcription result (when job is completed).

**Response:** Same as sync endpoint (transcription result)

#### `GET /api/v1/jobs`

List all jobs with optional filtering.

**Query parameters:**

- `status`: Filter by status (submitted, processing, completed, failed)
- `limit`: Number of jobs to return (default: 50)

#### `DELETE /api/v1/job/{job_id}`

Cancel a pending or processing job.

**Response:**

```json
{
  "status": "success",
  "job_id": "uuid-string",
  "message": "Job cancelled successfully"
}
```

#### `POST /api/v1/download-model/<model_name>`

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

## Scaling Workers

By default, docker-compose starts 2 Celery workers. To scale:

```bash
# Scale to 4 workers
docker-compose up -d --scale celery-worker-1=2 --scale celery-worker-2=2

# Or modify docker-compose.yml and add more worker services
```

Each worker processes one task at a time (concurrency=1) for optimal resource usage.

## Configuration

### Environment Variables

Key configuration variables (in docker-compose.yml or .env):

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000

# Paths
MODEL_PATH=/app/models
UPLOAD_PATH=/app/uploads

# Processing
THREADS=4                    # CPU threads per task
DEFAULT_MODEL=base.en

# Redis/Celery
REDIS_PASSWORD=whisper-redis-pass
CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...

# Logging
LOG_LEVEL=INFO
DEBUG=False
```

### Docker Compose Services

- **redis**: Message broker & result backend
- **whisper-api**: REST API server
- **celery-worker-1, celery-worker-2**: Background job processors

## When to Use Each Mode

### Use Synchronous (`/api/v1/transcribe`)

- Audio files < 10 minutes
- Need immediate response
- Simple integration
- Single user/request at a time

### Use Async (`/api/v1/transcribe-async`)

- Audio files > 10 minutes (up to 1+ hour)
- Multiple concurrent users
- Can poll for results
- Need job management
- Want to scale horizontally
- Handle long-running jobs gracefully
  "model_path": "/app/models",
  "threads": 4
  }

````

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
````

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
