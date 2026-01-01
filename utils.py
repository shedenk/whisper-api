"""
Utility functions for Whisper API
"""

import os
import requests
import logging
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from flask import jsonify

logger = logging.getLogger(__name__)

def download_file_from_url(url: str, upload_folder: str, max_size_bytes: int) -> str:
    """
    Download a file from a URL to the upload folder
    
    Args:
        url: URL of the file to download
        upload_folder: Target directory
        max_size_bytes: Maximum allowed file size in bytes
        
    Returns:
        Absolute path to the downloaded file
        
    Raises:
        ValueError: If file is too large or download fails
    """
    try:
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
            
        # Get filename from URL or use default
        filename = os.path.basename(parsed.path)
        if not filename:
            filename = "downloaded_audio"
        
        filename = secure_filename(filename)
        # Ensure extension exists if missing
        if not os.path.splitext(filename)[1]:
            filename += ".mp3"  # Default to mp3 if unknown
            
        filepath = os.path.join(upload_folder, filename)
        
        # Stream download to check size
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            
            # Check content length header if available
            if 'content-length' in r.headers:
                if int(r.headers['content-length']) > max_size_bytes:
                    raise ValueError(f"File too large. Maximum size: {max_size_bytes // (1024*1024)}MB")
            
            downloaded_size = 0
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    downloaded_size += len(chunk)
                    if downloaded_size > max_size_bytes:
                        f.close()
                        os.remove(filepath)
                        raise ValueError(f"File too large. Maximum size: {max_size_bytes // (1024*1024)}MB")
                    f.write(chunk)
                    
        return filepath
        
    except requests.RequestException as e:
        raise ValueError(f"Failed to download file: {str(e)}")
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise e

def error_response(message: str, status_code: int = 400):
    """Return a standardized JSON error response"""
    return jsonify({
        'status': 'error',
        'message': message
    }), status_code
