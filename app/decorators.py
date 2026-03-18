# app/decorators.py
import functools
import time
import random
from sqlalchemy.exc import OperationalError
from flask import flash, redirect, request

def with_db_retry(max_retries=3, delay=1.0, backoff=2.0):
    """
    Decorator to retry database operations on connection failures.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except OperationalError as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    # Check if it's a connection error worth retrying
                    is_retryable = any(keyword in error_str for keyword in [
                        'connection', 'timeout', 'refused', 'network',
                        'could not connect', 'server closed', 'ssl',
                        'neon', 'terminated unexpectedly', 'reset by peer'
                    ])
                    
                    if not is_retryable or attempt == max_retries:
                        break
                    
                    # Wait before retry with jitter
                    jitter = random.uniform(0, 0.5)
                    time.sleep(current_delay + jitter)
                    current_delay *= backoff
                    
                    # Log retry
                    from flask import current_app
                    current_app.logger.warning(
                        f"DB retry {attempt + 1}/{max_retries} for {func.__name__}: {str(e)[:100]}"
                    )
            
            # All retries exhausted
            from flask import current_app
            current_app.logger.error(f"DB operation failed after {max_retries} retries: {last_error}")
            
            # Handle based on request type
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({
                    'success': False,
                    'error': 'Network error. Please check your internet connection and try again.',
                    'retry': True
                }), 503
            
            flash('⚠️ Network error. Please check your internet connection and try again, or refresh the browser.', 'error')
            return redirect(request.referrer or '/dashboard')
            
        return wrapper
    return decorator