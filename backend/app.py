"""Flask Application for AI Image Studio."""

import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from config import Config
from cloudflare_client import CloudflareAIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_image_studio")

# Determine frontend directory
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

# Initialize Cloudflare AI Client
ai_client = CloudflareAIClient()


@app.route("/")
def index():
    """Serve the single-page frontend application."""
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    """Serve static assets (CSS, JS, images, fonts)."""
    file_path = FRONTEND_DIR / path
    if file_path.exists():
        return send_from_directory(str(FRONTEND_DIR), path)
    # Default fallback to index.html for SPA behavior
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    """Return backend status and API configuration state."""
    accounts = Config.get_cloudflare_accounts()
    configured = Config.is_configured()
    account_id_masked = ""
    if accounts:
        acc = accounts[0][0]
        account_id_masked = f"{acc[:4]}...{acc[-4:]}" if len(acc) > 8 else "***"

    gemini_keys = Config.get_gemini_keys()

    return jsonify({
        "status": "online",
        "configured": configured,
        "model": Config.CLOUDFLARE_MODEL,
        "total_cloudflare_accounts": len(accounts),
        "gemini_configured": bool(gemini_keys),
        "total_gemini_keys": len(gemini_keys),
        "pollinations_priority": bool(Config.POLLINATIONS_API_KEY),
        "account_id_masked": account_id_masked,
        "default_steps": Config.DEFAULT_STEPS,
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    """Handle image generation requests using FLUX.1 Schnell & failover pool."""
    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "Request body must be valid JSON.",
            "code": "INVALID_JSON"
        }), 400

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    style = data.get("style", "realistic")
    aspect_ratio = data.get("aspect_ratio", "square")
    steps = data.get("steps", Config.DEFAULT_STEPS)
    seed = data.get("seed", None)

    # Validation
    if not prompt:
        return jsonify({
            "success": False,
            "error": "Please enter a prompt describing the image you want to generate.",
            "code": "MISSING_PROMPT"
        }), 400

    if len(prompt) > Config.MAX_PROMPT_LENGTH:
        return jsonify({
            "success": False,
            "error": f"Prompt exceeds maximum allowed length of {Config.MAX_PROMPT_LENGTH} characters.",
            "code": "PROMPT_TOO_LONG"
        }), 400

    # Multi-account & failover client
    client = CloudflareAIClient()

    logger.info("Generating image for prompt: '%s...' | Style: %s | Aspect: %s", prompt[:40], style, aspect_ratio)
    
    success, result = client.generate_image(
        prompt=prompt,
        style=style,
        aspect_ratio=aspect_ratio,
        steps=steps,
        seed=seed
    )

    if not success:
        status_code = 400
        code = result.get("code", "")
        if code == "MISSING_CREDENTIALS":
            status_code = 401
        elif code in ("INVALID_TOKEN", "NOT_FOUND"):
            status_code = 401
        elif code == "RATE_LIMIT_EXCEEDED":
            status_code = 429
        elif code in ("REQUEST_TIMEOUT", "CONNECTION_ERROR", "SERVER_ERROR"):
            status_code = 502

        return jsonify({
            "success": False,
            "error": result.get("error", "Failed to generate image."),
            "code": code
        }), status_code

    return jsonify({
        "success": True,
        **result
    })


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found", "code": "NOT_FOUND"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error occurred.", "code": "SERVER_ERROR"}), 500


if __name__ == "__main__":
    print(f"Starting AI Image Studio server on http://127.0.0.1:{Config.PORT}")
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
