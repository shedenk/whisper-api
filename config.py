"""
Configuration module for Whisper.cpp API
"""

import os
from pathlib import Path


class Config:
    """Base configuration class"""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    JSON_SORT_KEYS = False
    
    # Upload and model paths
    UPLOAD_FOLDER = os.getenv('UPLOAD_PATH', '/app/uploads')
    MODEL_PATH = os.getenv('MODEL_PATH', '/app/models')
    
    # File upload settings
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size
    UPLOAD_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.wma', '.aac', '.webm'}
    
    # Whisper settings
    THREADS = int(os.getenv('THREADS', '4'))
    DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'base.en')
    
    # Server settings
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', '8000'))
    
    # Timeout settings (in seconds)
    TRANSCRIPTION_TIMEOUT = 600  # 10 minutes
    MODEL_DOWNLOAD_TIMEOUT = 3600  # 1 hour
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Redis & Celery settings
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    
    # Job settings
    JOB_RESULT_EXPIRY = 86400  # 24 hours
    MAX_CONCURRENT_JOBS = 10
    JOB_TIMEOUT = 1800  # 30 minutes


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = 'INFO'


class TestConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    UPLOAD_FOLDER = '/tmp/whisper-uploads'
    MODEL_PATH = '/tmp/whisper-models'
