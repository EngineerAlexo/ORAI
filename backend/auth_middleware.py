"""Authentication middleware for AI Studio Flask endpoints.
Verifies Firebase ID tokens and attaches user details to flask.request.
"""

from functools import wraps
from flask import request, jsonify, g
from firebase_service import verify_firebase_token
import logging

logger = logging.getLogger("ai_studio.auth")


def extract_token_from_request() -> str:
    """Extract Firebase ID token from Authorization header or custom headers."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    
    # Check alternate header
    custom_token = request.headers.get("X-Firebase-Token", "")
    if custom_token:
        return custom_token.strip()

    # Check query param (useful for downloads / previews)
    return request.args.get("token", "").strip()


def require_auth(f):
    """
    Decorator to protect endpoints.
    Requires a valid Firebase ID token in Authorization header.
    Attaches user data to `request.user` and `g.user`.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = extract_token_from_request()
        if not token:
            return jsonify({
                "success": False,
                "error": "Authentication required. Please log in to access AI Studio features.",
                "code": "AUTH_REQUIRED",
            }), 401

        user = verify_firebase_token(token)
        if not user:
            return jsonify({
                "success": False,
                "error": "Invalid or expired session. Please log in again.",
                "code": "INVALID_TOKEN",
            }), 401

        # Attach user to request context
        request.user = user
        g.user = user
        return f(*args, **kwargs)

    return decorated_function


def optional_auth(f):
    """
    Decorator for public endpoints that can optionally personalize content if logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = extract_token_from_request()
        request.user = verify_firebase_token(token) if token else None
        g.user = request.user
        return f(*args, **kwargs)

    return decorated_function
