"""Main entry point to start the AI Image Studio application."""

import sys
from pathlib import Path

# Add backend directory to sys.path so modules resolve correctly
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from config import Config
from app import app

if __name__ == "__main__":
    accounts = Config.get_cloudflare_accounts()
    print("=" * 60)
    print(" AI Studio - Image & Video Generative Platform")
    print("=" * 60)
    print(f" Web UI available at: http://127.0.0.1:{Config.PORT}")
    print(f" Firebase Project: {Config.FIREBASE_PROJECT_ID}")
    print(f" Cloudflare Accounts: {len(accounts)}")
    print(f" Gemini Imagen Keys: {len(Config.get_gemini_keys())}")
    print(f" Pollinations Turbo: {'[Active]' if Config.POLLINATIONS_API_KEY else '[Enabled]'}")
    print(f" Video Studio Engine: [Ready - T2V & I2V]")
    print(f" Daily Limits: {Config.DAILY_IMAGE_LIMIT} Images, {Config.DAILY_VIDEO_LIMIT} Videos")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
