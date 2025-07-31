"""Session and user utilities for Flask requests."""

from flask import request, session, g
from typing import Optional

def get_current_user_id() -> Optional[str]:
    """Get the current user ID from the request context."""
    try:
        # Try to get from request headers
        user_id = request.headers.get('X-User-ID')
        if user_id:
            return user_id
        
        # Try to get from request args
        user_id = request.args.get('user_id')
        if user_id:
            return user_id
        
        # Try to get from JSON body
        if request.is_json:
            data = request.get_json()
            if data and 'user_id' in data:
                return data['user_id']
        
        # Try to get from session
        if 'user_id' in session:
            return session['user_id']
        
        # Try to get from Flask g object
        if hasattr(g, 'user_id'):
            return g.user_id
        
        # Default fallback
        return "system"
        
    except Exception:
        return "system"

def get_current_session_id() -> Optional[str]:
    """Get the current session ID from the request context."""
    try:
        # Try to get from request headers
        session_id = request.headers.get('X-Session-ID')
        if session_id:
            return session_id
        
        # Try to get from request args
        session_id = request.args.get('session_id')
        if session_id:
            return session_id
        
        # Try to get from JSON body
        if request.is_json:
            data = request.get_json()
            if data and 'session_id' in data:
                return data['session_id']
        
        # Try to get from session
        if 'session_id' in session:
            return session['session_id']
        
        # Try to get from Flask g object
        if hasattr(g, 'session_id'):
            return g.session_id
        
        return None
        
    except Exception:
        return None

def set_user_context(user_id: str, session_id: str = None):
    """Set user context in Flask g object."""
    g.user_id = user_id
    if session_id:
        g.session_id = session_id
