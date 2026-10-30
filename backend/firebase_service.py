"""Firebase Authentication and Firestore Service for AI Studio.
Provides server-side token verification, user profile management, and database operations.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
import requests
import firebase_admin
from firebase_admin import auth as admin_auth, credentials, firestore
from config import Config

logger = logging.getLogger("ai_studio.firebase")

_firebase_app: Optional[firebase_admin.App] = None
_firestore_db = None


def initialize_firebase() -> bool:
    """Initialize Firebase Admin SDK if service account is provided, or prepare REST fallback."""
    global _firebase_app, _firestore_db

    if _firebase_app is not None:
        return True

    try:
        cred_path = Config.FIREBASE_CREDENTIALS_PATH
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred, {
                "projectId": Config.FIREBASE_PROJECT_ID,
                "storageBucket": Config.FIREBASE_STORAGE_BUCKET,
            })
            _firestore_db = firestore.client()
            logger.info("Firebase Admin SDK initialized with certificate: %s", cred_path)
            return True
        else:
            # Initialize with default options for project
            try:
                _firebase_app = firebase_admin.initialize_app(options={
                    "projectId": Config.FIREBASE_PROJECT_ID,
                })
                logger.info("Firebase Admin initialized with project: %s", Config.FIREBASE_PROJECT_ID)
                return True
            except Exception as default_err:
                logger.info("Firebase Admin default init skipped (%s). Using Google Identity REST verifier.", default_err)
                return True
    except Exception as err:
        logger.warning("Firebase Admin initialization note: %s", err)
        return False


def verify_firebase_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Firebase ID token.
    1. Attempts Firebase Admin SDK verify_id_token
    2. Fallbacks to Google Identity Toolkit REST API verification
    Returns user dict with {uid, email, name, email_verified} or None.
    """
    if not id_token or not id_token.strip():
        return None

    clean_token = id_token.strip()

    # 1. Try Firebase Admin SDK
    try:
        if _firebase_app:
            decoded = admin_auth.verify_id_token(clean_token)
            return {
                "uid": decoded.get("uid"),
                "email": decoded.get("email", ""),
                "name": decoded.get("name", ""),
                "email_verified": decoded.get("email_verified", False),
                "auth_time": decoded.get("auth_time"),
            }
    except Exception as admin_err:
        logger.debug("Admin SDK token verify failed, trying Google Identity REST: %s", admin_err)

    # 2. Resilient Google Identity Toolkit verification
    try:
        api_key = Config.FIREBASE_API_KEY
        if api_key:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={api_key}"
            res = requests.post(url, json={"idToken": clean_token}, timeout=10)
            if res.ok:
                data = res.json()
                users = data.get("users", [])
                if users:
                    u = users[0]
                    return {
                        "uid": u.get("localId"),
                        "email": u.get("email", ""),
                        "name": u.get("displayName", ""),
                        "email_verified": u.get("emailVerified", False),
                    }
            else:
                logger.warning("Google Identity verify rejected token: %s", res.text[:120])
    except Exception as rest_err:
        logger.error("REST token verification error: %s", rest_err)

    return None


def get_firestore_client():
    """Return Firestore client if initialized."""
    global _firestore_db
    return _firestore_db


# Initialize on import
initialize_firebase()
