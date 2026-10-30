"""Flask Application for AI Studio (Image & Video Studio).
Coordinates authentication, image generation, video synthesis, user galleries, and quotas.
"""

import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file, abort
from flask_cors import CORS

from config import Config
from auth_middleware import require_auth, optional_auth
from image_generator import image_generator
from video_generator import video_generator
from storage_manager import storage_manager
from usage_manager import usage_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_studio")

# Determine directories
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)


# =====================================================================
# Frontend Page Routing
# =====================================================================

@app.route("/")
def index():
    """Serve the studio portal / landing page."""
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/dashboard")
def dashboard_page():
    return send_from_directory(str(FRONTEND_DIR), "dashboard.html")


@app.route("/image-generator")
def image_gen_page():
    return send_from_directory(str(FRONTEND_DIR), "image-generator.html")


@app.route("/video-generator")
def video_gen_page():
    return send_from_directory(str(FRONTEND_DIR), "video-generator.html")


@app.route("/gallery")
def gallery_page():
    return send_from_directory(str(FRONTEND_DIR), "gallery.html")


@app.route("/account")
def account_page():
    return send_from_directory(str(FRONTEND_DIR), "account.html")


@app.route("/login")
def login_page():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.route("/register")
def register_page():
    return send_from_directory(str(FRONTEND_DIR), "register.html")


# =====================================================================
# System Status & Auth APIs
# =====================================================================

@app.route("/api/status", methods=["GET"])
def get_status():
    """Return backend status, AI providers configuration, and video readiness."""
    accounts = Config.get_cloudflare_accounts()
    gemini_keys = Config.get_gemini_keys()
    video_providers = video_generator.get_available_providers()

    return jsonify({
        "status": "online",
        "app_name": "AI Studio",
        "configured": Config.is_configured(),
        "total_cloudflare_accounts": len(accounts),
        "gemini_configured": bool(gemini_keys),
        "total_gemini_keys": len(gemini_keys),
        "pollinations_priority": bool(Config.POLLINATIONS_API_KEY),
        "video_providers": video_providers,
        "daily_limits": {
            "images": Config.DAILY_IMAGE_LIMIT,
            "videos": Config.DAILY_VIDEO_LIMIT,
        },
        "firebase_project": Config.FIREBASE_PROJECT_ID,
    })


@app.route("/api/auth/verify", methods=["POST"])
@require_auth
def verify_auth():
    """Verify current Firebase ID token and return user profile + usage statistics."""
    user = request.user
    stats = usage_manager.get_user_stats(user["uid"])
    return jsonify({
        "success": True,
        "user": user,
        "stats": stats,
    })


@app.route("/api/user/stats", methods=["GET"])
@require_auth
def get_user_stats():
    """Return generation stats and quotas for the authenticated user."""
    user = request.user
    stats = usage_manager.get_user_stats(user["uid"])
    return jsonify({
        "success": True,
        "stats": stats,
    })


# =====================================================================
# AI Image Generation API (Protected)
# =====================================================================

@app.route("/api/generate", methods=["POST"])
@require_auth
def generate_image():
    """Generate an AI image with quota enforcement and auto-save to user gallery."""
    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "Request body must be valid JSON.",
            "code": "INVALID_JSON"
        }), 400

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    style = data.get("style", "realistic")
    aspect_ratio = data.get("aspect_ratio", "1:1")
    negative_prompt = data.get("negative_prompt", "").strip()
    steps = data.get("steps", Config.DEFAULT_STEPS)
    seed = data.get("seed", None)
    user_id = request.user["uid"]

    # Input validation
    if not prompt:
        return jsonify({
            "success": False,
            "error": "Please enter a prompt describing the image you want to create.",
            "code": "MISSING_PROMPT"
        }), 400

    if len(prompt) > Config.MAX_PROMPT_LENGTH:
        return jsonify({
            "success": False,
            "error": f"Prompt exceeds maximum allowed length of {Config.MAX_PROMPT_LENGTH} characters.",
            "code": "PROMPT_TOO_LONG"
        }), 400

    logger.info("Image generation request for user %s: prompt='%s...' style=%s ratio=%s",
                user_id[:8], prompt[:30], style, aspect_ratio)

    success, result = image_generator.generate_image_for_user(
        user_id=user_id,
        prompt=prompt,
        style=style,
        aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt,
        steps=steps,
        seed=seed,
    )

    if not success:
        code = result.get("code", "")
        status_code = 400
        if code == "QUOTA_EXCEEDED":
            status_code = 429
        elif code in ("INVALID_TOKEN", "MISSING_CREDENTIALS"):
            status_code = 401
        elif code == "ALL_PROVIDERS_UNAVAILABLE":
            status_code = 503

        safe_result = {k: v for k, v in result.items() if k not in ("error", "code") and not isinstance(v, bytes)}
        return jsonify({
            "success": False,
            "error": result.get("error", "Image generation failed."),
            "code": code,
            **safe_result,
        }), status_code

    # Return result with saved gallery record
    safe_result = {k: v for k, v in result.items() if not isinstance(v, bytes)}
    return jsonify({
        "success": True,
        **safe_result
    })


# =====================================================================
# AI Video Generation APIs (Protected, Asynchronous)
# =====================================================================

@app.route("/api/video/generate", methods=["POST"])
@require_auth
def generate_video():
    """Queue a video generation task (Text-to-Video or Image-to-Video)."""
    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "Request body must be valid JSON.",
            "code": "INVALID_JSON"
        }), 400

    data = request.get_json() or {}
    user_id = request.user["uid"]
    mode = data.get("mode", "text-to-video")
    prompt = data.get("prompt", "").strip()
    negative_prompt = data.get("negative_prompt", "").strip()
    aspect_ratio = data.get("aspect_ratio", "16:9")
    duration = max(2, min(int(data.get("duration", 4)), 10))
    image_data = data.get("image_data", None)

    # Quota check
    allowed, quota_info = usage_manager.check_quota(user_id, "video")
    if not allowed:
        return jsonify({
            "success": False,
            "error": f"Daily video generation limit reached ({quota_info['limit']} videos/day). Resets at midnight UTC.",
            "code": "QUOTA_EXCEEDED",
            "quota": quota_info,
        }), 429

    # Validation
    if not prompt:
        return jsonify({
            "success": False,
            "error": "A prompt describing the scene or animation is required.",
            "code": "MISSING_PROMPT"
        }), 400

    if mode == "image-to-video" and not image_data:
        return jsonify({
            "success": False,
            "error": "Please provide an image for Image-to-Video animation.",
            "code": "MISSING_IMAGE"
        }), 400

    # Create asynchronous background job
    job = video_generator.create_video_job(
        user_id=user_id,
        mode=mode,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        duration=duration,
        image_data=image_data,
        negative_prompt=negative_prompt,
    )

    return jsonify({
        "success": True,
        "job_id": job["job_id"],
        "status": job["status"],
        "message": "Video synthesis job created.",
    })


@app.route("/api/video/status/<job_id>", methods=["GET"])
@require_auth
def get_video_job_status(job_id):
    """Poll the status and progress of a video generation job."""
    user_id = request.user["uid"]
    job = video_generator.get_job_status(job_id, user_id)
    if not job:
        return jsonify({
            "success": False,
            "error": "Video job not found or does not belong to your account.",
            "code": "JOB_NOT_FOUND"
        }), 404

    return jsonify({
        "success": True,
        "job": job,
    })


# =====================================================================
# User Gallery & Media Serving APIs (Protected)
# =====================================================================

@app.route("/api/gallery", methods=["GET"])
@require_auth
def get_gallery():
    """Retrieve personal isolated gallery for authenticated user."""
    user_id = request.user["uid"]
    media_type = request.args.get("type", None)
    items = storage_manager.get_user_gallery(user_id, media_type)

    return jsonify({
        "success": True,
        "gallery": items,
        "total": len(items),
    })


@app.route("/api/gallery/<media_id>", methods=["DELETE"])
@require_auth
def delete_gallery_item(media_id):
    """Delete an item from the user's gallery."""
    user_id = request.user["uid"]
    deleted = storage_manager.delete_user_media(user_id, media_id)
    if not deleted:
        return jsonify({
            "success": False,
            "error": "Item not found in your gallery.",
            "code": "ITEM_NOT_FOUND"
        }), 404

    return jsonify({
        "success": True,
        "message": "Media deleted successfully.",
    })


@app.route("/api/media/<media_type>/<safe_uid>/<filename>")
def serve_media_file(media_type, safe_uid, filename):
    """Safely serve stored image or video files."""
    if media_type not in ("image", "video"):
        abort(404)

    target_dir = Config.MEDIA_VIDEOS_DIR if media_type == "video" else Config.MEDIA_IMAGES_DIR
    user_dir = target_dir / safe_uid
    file_path = user_dir / filename

    if not file_path.exists():
        abort(404)

    mimetype = "video/mp4" if media_type == "video" else "image/jpeg"
    return send_file(str(file_path), mimetype=mimetype)


# =====================================================================
# Static Files Proxy
# =====================================================================

@app.route("/<path:path>")
def static_proxy(path):
    """Serve frontend static assets."""
    file_path = FRONTEND_DIR / path
    if file_path.exists():
        return send_from_directory(str(FRONTEND_DIR), path)
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found", "code": "NOT_FOUND"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error occurred.", "code": "SERVER_ERROR"}), 500


if __name__ == "__main__":
    print("=" * 60)
    print(f" AI Studio server listening on http://127.0.0.1:{Config.PORT}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
