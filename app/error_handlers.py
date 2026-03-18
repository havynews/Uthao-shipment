# app/error_handlers.py
from flask import Flask, render_template, request, flash, redirect, current_app
from sqlalchemy.exc import OperationalError, TimeoutError, DisconnectionError
from psycopg2 import OperationalError as Psycopg2OpError
import logging

logger = logging.getLogger(__name__)

def register_error_handlers(app):
    """Register global error handlers for the Flask app."""
    
    @app.errorhandler(OperationalError)
    @app.errorhandler(TimeoutError)
    @app.errorhandler(DisconnectionError)
    @app.errorhandler(Psycopg2OpError)
    def handle_database_error(error):
        """Handle database connection errors gracefully."""
        
        # Log the actual error for debugging
        logger.error(f"Database connection error: {str(error)}")
        
        # Check if it's a connection-related error
        error_str = str(error).lower()
        is_connection_error = any(keyword in error_str for keyword in [
            'connection', 'timeout', 'refused', 'network', 
            'could not connect', 'server closed', 'ssl',
            'neon', 'terminated unexpectedly'
        ])
        
        if is_connection_error or request.is_json:
            # For API/AJAX requests, return JSON response
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {
                    'success': False,
                    'error': 'Network error. Please check your internet connection and try again.',
                    'retry': True
                }, 503
            
            # For regular requests, flash message and redirect back
            flash('⚠️ Network error. Please check your internet connection and try again, or refresh the browser.', 'error')
            
            # Try to redirect back to the referring page
            referer = request.headers.get('Referer')
            if referer:
                return redirect(referer)
            
            # Fallback to dashboard or login
            if current_app.config.get('LOGIN_DISABLED'):
                return redirect('/')
            return redirect('/dashboard')
        
        # For other database errors, re-raise to be handled by default handler
        raise error
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle generic 500 errors, checking if they're database-related."""
        
        # Check if the original exception was a DB error
        original_error = getattr(error, 'original_exception', error)
        
        if isinstance(original_error, (OperationalError, TimeoutError, 
                                       DisconnectionError, Psycopg2OpError)):
            return handle_database_error(original_error)
        
        # Log unexpected errors
        logger.error(f"Unexpected 500 error: {str(error)}")
        
        # For production, show generic message
        if not app.debug:
            flash('An unexpected error occurred. Please try again later.', 'error')
            referer = request.headers.get('Referer')
            if referer:
                return redirect(referer)
            return redirect('/dashboard')
        
        # In debug mode, re-raise to see the full traceback
        raise error
    
    @app.errorhandler(503)
    def handle_service_unavailable(error):
        """Handle service unavailable errors."""
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {
                'success': False,
                'error': 'Service temporarily unavailable. Please try again.',
                'retry': True
            }, 503
        
        flash('⚠️ Service temporarily unavailable. Please try again in a moment.', 'error')
        referer = request.headers.get('Referer')
        if referer:
            return redirect(referer)
        return redirect('/dashboard')