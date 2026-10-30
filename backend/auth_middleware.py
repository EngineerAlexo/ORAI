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
    If a valid Firebase ID token is provided, attaches the authenticated user.
    If no token or invalid token is provided, gracefully falls back to a guest user
    session so users can immediately generate without friction.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = extract_token_from_request()
        user = None
        if token:
            user = verify_firebase_token(token)

        if not user:
            # Create a consistent guest identity from client IP
            raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
            client_ip = raw_ip.split(",")[0].strip()
            clean_ip = "".join(c for c in client_ip if c.isalnum() or c in ("-", "_")) or "127_0_0_1"
            guest_uid = f"guest_{clean_ip}"
            user = {
                "uid": guest_uid,
                "email": "guest@aistudio.local",
                "name": "Guest Creator",
                "is_guest": True,
            }

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
