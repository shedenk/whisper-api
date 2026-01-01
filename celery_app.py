"""
Celery application configuration
Handles async task setup and configuration
"""

import os
from celery import Celery

# Initialize Celery app
app = Celery('whisper_api', include=['celery_worker'])

# Load configuration from environment
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 hours hard limit
    task_soft_time_limit=3600,  # 1 hour soft limit
    result_expires=86400,  # Results expire after 24 hours (matches JOB_RESULT_EXPIRY)
    worker_prefetch_multiplier=1,  # Fetch one task at a time
    worker_max_tasks_per_child=1000,
    task_compression='gzip',
)

if __name__ == '__main__':
    app.start()
