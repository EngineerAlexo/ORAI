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
    print(" ORAI - Generative AI Studio")
    print("=" * 60)
    print(f" Web UI available at: http://127.0.0.1:{Config.PORT}")
    print(f" Cloudflare Accounts Active: {len(accounts)}")
    print(f" Gemini Imagen Fallback: {'[Enabled]' if Config.get_gemini_keys() else '[Disabled]'}")
    print(f" Pollinations FLUX: {'[Priority Turbo API Active]' if Config.POLLINATIONS_API_KEY else '[Enabled]'}")
    print(f" Primary Model: {Config.CLOUDFLARE_MODEL}")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
