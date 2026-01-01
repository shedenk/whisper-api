#!/usr/bin/env python3
"""
Whisper.cpp REST API Server
Provides transcription services using whisper.cpp with async job support
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
from functools import lru_cache

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
import redis

from config import Config
from celery_app import app as celery_app
from celery_worker import transcribe_audio_task

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Configure logging
logging.basicConfig(
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis connection with connection pooling
try:
    redis_client = redis.from_url(
        app.config['REDIS_URL'],
        max_connections=50,
        decode_responses=True  # Auto decode bytes to strings
    )
    redis_client.ping()
    logger.info("Connected to Redis")
except Exception as e:
    logger.warning(f"Could not connect to Redis: {e}")
    redis_client = None

# Create directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MODEL_PATH'], exist_ok=True)

# Whisper.cpp paths
WHISPER_MAIN = '/app/whisper.cpp/main'
WHISPER_MODELS_DIR = '/app/whisper.cpp/models'

# Debug: Check if whisper binary exists
if os.path.exists(WHISPER_MAIN):
    logger.info(f"Whisper binary found at {WHISPER_MAIN}")
else:
    logger.error(f"Whisper binary NOT found at {WHISPER_MAIN}")
    # List directory contents to debug
    parent_dir = os.path.dirname(WHISPER_MAIN)
    if os.path.exists(parent_dir):
        logger.info(f"Contents of {parent_dir}: {os.listdir(parent_dir)}")
        # Check for bin directory just in case
        bin_dir = os.path.join(parent_dir, 'bin')
        if os.path.exists(bin_dir):
            logger.info(f"Contents of {bin_dir}: {os.listdir(bin_dir)}")
    else:
        logger.error(f"Parent directory {parent_dir} does not exist!")


class WhisperError(Exception):
    """Custom exception for Whisper operations"""
    pass


@lru_cache(maxsize=1)
def get_available_models():
    """Get list of available Whisper models"""
    models = []
    
    # Check models in whisper.cpp directory
    if os.path.exists(WHISPER_MODELS_DIR):
        for model_file in os.listdir(WHISPER_MODELS_DIR):
            if model_file.endswith('.bin'):
                models.append(model_file)
    
    # Check custom models directory
    if os.path.exists(app.config['MODEL_PATH']):
        for model_file in os.listdir(app.config['MODEL_PATH']):
            if model_file.endswith('.bin'):
                models.append(model_file)
    
    return sorted(list(set(models)))


def validate_audio_file(filepath: str) -> bool:
    """Validate that file is a valid audio format"""
    valid_extensions = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.wma', '.aac'}
    ext = Path(filepath).suffix.lower()
    return ext in valid_extensions


def transcribe_audio(audio_path: str, model: str = 'base.en', language: Optional[str] = None) -> dict:
    """
    Transcribe audio file using whisper.cpp
    
    Args:
        audio_path: Path to audio file
        model: Model name (base, small, medium, large, tiny, etc.)
        language: Optional language code (e.g., 'en', 'es', 'fr')
    
    Returns:
        Dictionary with transcription results
    """
    
    if not os.path.exists(audio_path):
        raise WhisperError(f"Audio file not found: {audio_path}")
    
    if not validate_audio_file(audio_path):
        raise WhisperError("Invalid audio file format")
    
    try:
        # Resolve model path
        from utils import resolve_model_path
        model_path = resolve_model_path(model, WHISPER_MODELS_DIR, app.config['MODEL_PATH'])
        
        if not os.path.exists(model_path):
             raise WhisperError(f"Model file not found: {model_path}")

        # Build whisper command
        cmd = [WHISPER_MAIN, '-m', model_path, '-f', audio_path]
        
        if language:
            cmd.extend(['-l', language])
        
        cmd.extend(['--output-json', '--threads', str(app.config['THREADS'])])
        
        logger.info(f"Running transcription: {' '.join(cmd)}")
        
        # Run whisper
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise WhisperError(f"Transcription failed: {error_msg}")
        
        # Parse JSON output
        output_json_path = audio_path.replace(Path(audio_path).suffix, '.json')
        
        if os.path.exists(output_json_path):
            with open(output_json_path, 'r') as f:
                data = json.load(f)
            
            # Clean up JSON output file
            os.remove(output_json_path)
            
            # Extract text and segments from whisper output
            # Handle different output formats
            transcription_text = ''
            segments = []
            
            if 'result' in data and isinstance(data['result'], list):
                segments = data['result']
                # Combine all segment text
                transcription_text = ' '.join([seg.get('text', '').strip() for seg in segments if seg.get('text')])
            elif 'transcription' in data:
                transcription_text = data.get('transcription', '')
                segments = data.get('segments', [])
            
            return {
                'status': 'success',
                'text': transcription_text,
                'segments': segments,
                'model': model,
                'language': language or 'auto'
            }
        else:
            raise WhisperError("No output generated from whisper")
            
    except subprocess.TimeoutExpired:
        raise WhisperError("Transcription timeout (10 minutes exceeded)")
    except Exception as e:
        raise WhisperError(f"Transcription error: {str(e)}")


# ========================
# API Routes
# ========================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'whisper-api'
    }), 200


@app.route('/api/v1/models', methods=['GET'])
def list_models():
    """List available Whisper models"""
    try:
        models = get_available_models()
        
        # If no models found, list supported models
        if not models:
            supported = ['tiny.en', 'base.en', 'small.en', 'medium.en', 
                        'tiny', 'base', 'small', 'medium', 'large']
            return jsonify({
                'status': 'success',
                'models': supported,
                'downloaded': [],
                'message': 'No models downloaded. Use /api/v1/download-model to download.'
            }), 200
        
        return jsonify({
            'status': 'success',
            'models': models,
            'count': len(models)
        }), 200
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/transcribe', methods=['POST'])
def transcribe():
    """
    Transcribe audio file
    
    Request:
        - file: Audio file (multipart)
        - model: Model name (default: base.en)
        - language: Language code (optional, e.g., en, es, fr)
    """
    try:
        # Handle input: either file upload or URL
        filepath = None
        
        # Get form data or JSON data
        data = request.form
        if request.is_json:
            data = request.get_json()
        
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'status': 'error', 'message': 'Empty filename'}), 400
            
            # Validate file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > app.config['MAX_CONTENT_LENGTH']:
                return jsonify({
                    'status': 'error',
                    'message': f'File too large. Maximum size: {app.config["MAX_CONTENT_LENGTH"] / (1024*1024):.0f}MB'
                }), 413
            
            if file_size == 0:
                return jsonify({'status': 'error', 'message': 'Empty file'}), 400
                
            # Save uploaded file
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp + filename)
            file.save(filepath)
            
        elif 'file_url' in data:
            file_url = data['file_url']
            try:
                from utils import download_file_from_url
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                temp_filename = f"{timestamp}_url_download"
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
                
                # Download using utility (it handles size validation)
                filepath = download_file_from_url(
                    file_url, 
                    app.config['UPLOAD_FOLDER'], 
                    app.config['MAX_CONTENT_LENGTH']
                )
                
                # Rename to add timestamp if not already added by download util
                start_path = filepath
                filename = os.path.basename(filepath)
                if not filename.startswith(timestamp):
                    new_path = os.path.join(app.config['UPLOAD_FOLDER'], timestamp + filename)
                    os.rename(start_path, new_path)
                    filepath = new_path
                    
                logger.info(f"File downloaded from URL: {filepath}")
                
            except ValueError as e:
                return jsonify({'status': 'error', 'message': str(e)}), 400
            except Exception as e:
                logger.error(f"Download failed: {e}")
                return jsonify({'status': 'error', 'message': 'Failed to process URL'}), 500
        else:
            return jsonify({
                'status': 'error',
                'message': 'No audio file or URL provided. Send "file" or "file_url"'
            }), 400
        
        logger.info(f"Processing file: {filepath}")
        
        # Get parameters
        model = data.get('model', 'base.en')
        language = data.get('language', None)
        
        # Validate model exists (basic check)
        model_name = model if model.endswith('.bin') else f"{model}.bin"
        if not (os.path.exists(f"{WHISPER_MODELS_DIR}/{model_name}") or 
                os.path.exists(f"{app.config['MODEL_PATH']}/{model_name}")):
            logger.warning(f"Model {model} may not be available")
        
        # Transcribe
        result = transcribe_audio(filepath, model=model, language=language)
        
        # Cleanup
        try:
            os.remove(filepath)
        except OSError as e:
            logger.warning(f"Failed to remove uploaded file {filepath}: {e}")
        
        return jsonify(result), 200
        
    except WhisperError as e:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        logger.error(f"Whisper error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/download-model/<model_name>', methods=['POST'])
def download_model(model_name):
    """Download a specific Whisper model"""
    try:
        model_name = secure_filename(model_name)
        
        # Import utility
        from utils import resolve_model_path
        
        # Define model URL (HuggingFace)
        target_file = f"ggml-{model_name}.bin"
        if model_name.endswith('.bin'):
            target_file = model_name
            
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{target_file}"
        
        logger.info(f"Downloading model {model_name} from {url}")
        
        # Save to CUSTOM model path (mounted volume) so user can see it
        # This fixes "empty models folder" issue
        save_path = os.path.join(app.config['MODEL_PATH'], target_file)
        
        if os.path.exists(save_path):
             logger.info(f"Model {model_name} already exists at {save_path}")
             return jsonify({
                'status': 'success',
                'message': f'Model {model_name} already exists'
            }), 200

        # Stream download
        with requests.get(url, stream=True, timeout=3600) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        logger.info(f"Model downloaded to {save_path}")
        
        # Clear model cache
        get_available_models.cache_clear()
        
        return jsonify({
            'status': 'success',
            'message': f'Model {model_name} downloaded successfully'
        }), 200
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading model: {e}")
        return jsonify({
            'status': 'error',
            'message': f"Download failed: {str(e)}"
        }), 500
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/info', methods=['GET'])
def get_info():
    """Get API and system information"""
    return jsonify({
        'status': 'success',
        'api_version': '1.0.0',
        'service': 'Whisper.cpp API',
        'timestamp': datetime.utcnow().isoformat(),
        'upload_path': app.config['UPLOAD_FOLDER'],
        'model_path': app.config['MODEL_PATH'],
        'threads': app.config['THREADS'],
        'async_enabled': redis_client is not None
    }), 200


# ========================
# Async API Endpoints
# ========================

@app.route('/api/v1/transcribe-async', methods=['POST'])
def transcribe_async():
    """
    Submit audio file for async transcription
    Returns immediately with a job ID for polling
    
    Request:
        - file: Audio file (multipart)
        - model: Model name (default: base.en)
        - language: Language code (optional)
    
    Response:
        {
            'status': 'submitted',
            'job_id': 'uuid',
            'message': 'Job submitted for processing',
            'poll_url': '/api/v1/job/{job_id}'
        }
    """
    
    if not redis_client:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available (Redis not connected)'
        }), 503
    
    try:
        # Handle input: either file upload or URL
        filepath = None
        filename = None
        
        # Get form data or JSON data
        data = request.form
        if request.is_json:
            data = request.get_json()
        
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'status': 'error', 'message': 'Empty filename'}), 400
                
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp + filename)
            file.save(filepath)
            
        elif 'file_url' in data:
            file_url = data['file_url']
            try:
                from utils import download_file_from_url
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                
                # Download using utility
                filepath = download_file_from_url(
                    file_url, 
                    app.config['UPLOAD_FOLDER'], 
                    app.config['MAX_CONTENT_LENGTH']
                )
                
                # Rename if needed
                start_path = filepath
                filename = os.path.basename(filepath)
                if not filename.startswith(timestamp):
                    new_path = os.path.join(app.config['UPLOAD_FOLDER'], timestamp + filename)
                    os.rename(start_path, new_path)
                    filepath = new_path
                    filename = os.path.basename(filepath)
                    
                logger.info(f"File downloaded from URL for async: {filepath}")
                
            except ValueError as e:
                return jsonify({'status': 'error', 'message': str(e)}), 400
        else:
            return jsonify({
                'status': 'error',
                'message': 'No audio file or URL provided. Send "file" or "file_url"'
            }), 400
            
        logger.info(f"Processing async file: {filepath}")
        
        # Get parameters
        model = data.get('model', 'base.en')
        language = data.get('language', None)
        
        # Submit task to Celery
        task = transcribe_audio_task.delay(
            audio_path=filepath,
            model=model,
            language=language,
            job_metadata={
                'filename': filename,
                'file_size': os.path.getsize(filepath),
                'submitted_at': datetime.utcnow().isoformat()
            }
        )
        
        job_id = task.id
        
        # Store job metadata in Redis
        if redis_client:
            redis_client.hset(f'job:{job_id}', mapping={
                'status': 'submitted',
                'model': model,
                'language': language or 'auto',
                'filename': filename,
                'submitted_at': datetime.utcnow().isoformat()
            })
            redis_client.expire(f'job:{job_id}', app.config['JOB_RESULT_EXPIRY'])
        
        logger.info(f"Task submitted with ID: {job_id}")
        
        return jsonify({
            'status': 'submitted',
            'job_id': job_id,
            'message': 'Job submitted for processing',
            'poll_url': f'/api/v1/job/{job_id}',
            'result_url': f'/api/v1/result/{job_id}'
        }), 202
        
    except Exception as e:
        # Cleanup file if submission failed
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
                
        logger.error(f"Error submitting async job: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/job/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get status of a transcription job
    
    Response:
        {
            'status': 'submitted|processing|completed|failed',
            'job_id': 'uuid',
            'progress': 0-100,
            'message': 'Status message'
        }
    """
    
    if not redis_client:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available'
        }), 503
    
    try:
        # Get task state from Celery
        task = celery_app.AsyncResult(job_id)
        
        # Get metadata from Redis
        job_data = redis_client.hgetall(f'job:{job_id}')
        
        if not job_data:
            return jsonify({
                'status': 'error',
                'message': 'Job not found'
            }), 404
        
        response = {
            'job_id': job_id,
            'celery_status': task.state,
            'submitted_at': job_data.get('submitted_at', ''),
            'model': job_data.get('model', ''),
            'language': job_data.get('language', '')
        }
        
        # Map Celery states to custom status
        if task.state == 'PENDING':
            response['status'] = 'queued'
            response['progress'] = 0
            response['message'] = 'Job is queued'
        elif task.state == 'PROCESSING':
            response['status'] = 'processing'
            response['progress'] = task.info.get('progress', 30) if isinstance(task.info, dict) else 30
            response['message'] = task.info.get('status', 'Processing') if isinstance(task.info, dict) else 'Processing'
        elif task.state == 'SUCCESS':
            response['status'] = 'completed'
            response['progress'] = 100
            response['message'] = 'Transcription completed'
            response['result_url'] = f'/api/v1/result/{job_id}'
        elif task.state == 'FAILURE':
            response['status'] = 'failed'
            response['progress'] = 0
            response['message'] = str(task.info) if task.info else 'Unknown error'
        else:
            response['status'] = task.state.lower()
            response['progress'] = 0
            response['message'] = str(task.info)
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/result/<job_id>', methods=['GET'])
def get_job_result(job_id):
    """
    Get transcription result for completed job
    
    Response: Transcription result with segments
    """
    
    if not redis_client:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available'
        }), 503
    
    try:
        # Get task state
        task = celery_app.AsyncResult(job_id)
        
        if task.state == 'SUCCESS':
            # Return the result
            return jsonify(task.result), 200
        elif task.state == 'FAILURE':
            return jsonify({
                'status': 'error',
                'job_id': job_id,
                'message': str(task.info)
            }), 400
        elif task.state == 'PENDING':
            return jsonify({
                'status': 'error',
                'job_id': job_id,
                'message': 'Job not yet started'
            }), 202
        else:
            return jsonify({
                'status': 'error',
                'job_id': job_id,
                'message': f'Job still processing (state: {task.state})'
            }), 202
            
    except Exception as e:
        logger.error(f"Error getting job result: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/job/<job_id>', methods=['DELETE'])
def cancel_job(job_id):
    """
    Cancel a pending or processing transcription job
    """
    
    if not redis_client:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available'
        }), 503
    
    try:
        # Get task
        task = celery_app.AsyncResult(job_id)
        
        # Check if job exists
        job_data = redis_client.hgetall(f'job:{job_id}')
        if not job_data:
            return jsonify({
                'status': 'error',
                'message': 'Job not found'
            }), 404
        
        # Revoke task
        task.revoke(terminate=True, signal='SIGKILL')
        
        # Update job status
        redis_client.hset(f'job:{job_id}', 'status', 'cancelled')
        
        logger.info(f"Job {job_id} cancelled")
        
        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'message': 'Job cancelled successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Error cancelling job: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/v1/jobs', methods=['GET'])
def list_jobs():
    """
    List all active and recent jobs
    
    Query parameters:
        - status: Filter by status (submitted, processing, completed, failed)
        - limit: Number of jobs to return (default: 50)
    """
    
    if not redis_client:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available'
        }), 503
    
    try:
        status_filter = request.args.get('status', None)
        limit = int(request.args.get('limit', 50))
        
        # Get all job keys
        job_keys = redis_client.keys('job:*')
        
        jobs = []
        for key in job_keys[:limit]:
            job_id = key.decode() if isinstance(key, bytes) else key
            job_id = job_id.replace('job:', '')
            job_data = redis_client.hgetall(f'job:{job_id}')
            
            task = celery_app.AsyncResult(job_id)
            
            job_info = {
                'job_id': job_id,
                'celery_status': task.state,
                'submitted_at': job_data.get('submitted_at', ''),
                'model': job_data.get('model', ''),
                'filename': job_data.get('filename', '')
            }
            
            # Add Celery state
            if task.state == 'SUCCESS':
                job_info['status'] = 'completed'
            elif task.state == 'FAILURE':
                job_info['status'] = 'failed'
            elif task.state == 'PROCESSING':
                job_info['status'] = 'processing'
            else:
                job_info['status'] = 'queued'
            
            if not status_filter or job_info['status'] == status_filter:
                jobs.append(job_info)
        
        return jsonify({
            'status': 'success',
            'jobs': jobs,
            'count': len(jobs)
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    logger.error(f"Server error: {error}")
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500


if __name__ == '__main__':
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Whisper.cpp API server on {host}:{port}")
    logger.info(f"Models directory: {app.config['MODEL_PATH']}")
    logger.info(f"Upload directory: {app.config['UPLOAD_FOLDER']}")
    
    app.run(host=host, port=port, debug=debug)
