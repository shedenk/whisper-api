"""
Celery worker tasks
Contains background job definitions for audio transcription
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime

from celery import shared_task
from celery.utils.log import get_task_logger
import redis

from celery_app import app
from config import Config

# Configure logging
logger = get_task_logger(__name__)

# Whisper.cpp paths
WHISPER_MAIN = '/app/whisper.cpp/main'

# Redis connection for metadata storage
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url)


class TranscriptionError(Exception):
    """Custom exception for transcription errors"""
    pass


@shared_task(bind=True, name='transcribe_audio')
def transcribe_audio_task(self, audio_path: str, model: str = 'base.en', 
                          language: str = None, job_metadata: dict = None):
    """
    Background task for audio transcription using whisper.cpp
    
    Args:
        audio_path: Path to audio file
        model: Whisper model name
        language: Optional language code
        job_metadata: Metadata about the job
        
    Returns:
        Dictionary with transcription results
    """
    
    job_id = self.request.id
    
    try:
        # Update task state
        self.update_state(
            state='PROCESSING',
            meta={'status': 'Starting transcription', 'progress': 10}
        )
        
        logger.info(f"[{job_id}] Starting transcription: {audio_path}")
        logger.info(f"[{job_id}] Model: {model}, Language: {language}")
        
        # Validate file exists
        if not os.path.exists(audio_path):
            raise TranscriptionError(f"Audio file not found: {audio_path}")
        
        # Get file info
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"[{job_id}] File size: {file_size_mb:.2f}MB")
        
        # Build whisper command
        cmd = [WHISPER_MAIN, '-m', model, audio_path]
        
        if language:
            cmd.extend(['-l', language])
        
        threads = int(os.getenv('THREADS', 4))
        cmd.extend(['--output-json', '--threads', str(threads)])
        
        logger.info(f"[{job_id}] Command: {' '.join(cmd)}")
        
        # Update state - starting processing
        self.update_state(
            state='PROCESSING',
            meta={'status': 'Processing audio', 'progress': 30}
        )
        
        # Run whisper.cpp
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout for long files
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            logger.error(f"[{job_id}] Transcription failed: {error_msg}")
            raise TranscriptionError(f"Transcription failed: {error_msg}")
        
        logger.info(f"[{job_id}] Whisper.cpp completed successfully")
        
        # Parse JSON output
        output_json_path = audio_path.replace(Path(audio_path).suffix, '.json')
        
        if not os.path.exists(output_json_path):
            raise TranscriptionError("No output generated from whisper")
        
        # Read results
        with open(output_json_path, 'r') as f:
            data = json.load(f)
        
        # Clean up JSON output file
        try:
            os.remove(output_json_path)
        except OSError as e:
            logger.warning(f"[{job_id}] Failed to remove JSON output: {e}")
        
        # Extract transcription text
        transcription_text = ''
        segments = []
        
        if data.get('result'):
            segments = data.get('result', [])
            # Combine all segment text
            transcription_text = ' '.join([seg.get('text', '').strip() 
                                          for seg in segments])
        
        logger.info(f"[{job_id}] Transcription text length: {len(transcription_text)}")
        logger.info(f"[{job_id}] Number of segments: {len(segments)}")
        
        # Prepare result
        result_data = {
            'status': 'success',
            'job_id': job_id,
            'text': transcription_text,
            'segments': segments,
            'model': model,
            'language': language or 'auto',
            'file_size_mb': file_size_mb,
            'segment_count': len(segments),
            'completed_at': datetime.utcnow().isoformat()
        }
        
        # Store metadata in Redis
        redis_client.hset(f'job:{job_id}', mapping={
            'status': 'completed',
            'result': json.dumps(result_data),
            'completed_at': datetime.utcnow().isoformat()
        })
        
        logger.info(f"[{job_id}] Transcription completed successfully")
        
        return result_data
        
    except subprocess.TimeoutExpired:
        error_msg = "Transcription timeout (30 minutes exceeded)"
        logger.error(f"[{job_id}] {error_msg}")
        raise TranscriptionError(error_msg)
        
    except Exception as e:
        error_msg = f"Transcription error: {str(e)}"
        logger.error(f"[{job_id}] {error_msg}")
        raise TranscriptionError(error_msg)
        
    finally:
        # Clean up audio file
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"[{job_id}] Cleaned up audio file")
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to clean up file: {str(e)}")


@app.task(bind=True, name='cleanup_old_jobs')
def cleanup_old_jobs(self):
    """
    Cleanup old job metadata from Redis
    Runs periodically to clean up expired results
    """
    try:
        logger.info("Starting cleanup of old jobs")
        
        # Find all job keys
        job_keys = redis_client.keys('job:*')
        
        cleaned = 0
        for key in job_keys:
            # Check if result exists and is old
            ttl = redis_client.ttl(key)
            
            if ttl == -1:  # No expiration set
                # Set 24 hour expiration
                redis_client.expire(key, 86400)
                cleaned += 1
        
        logger.info(f"Cleanup complete: {cleaned} jobs updated")
        
        return {
            'status': 'success',
            'jobs_cleaned': cleaned
        }
        
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }
