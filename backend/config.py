"""Configuration module for ORAI backend with multi-account and multi-provider support."""

import os
from typing import List, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
BACKEND_ENV_PATH = Path(__file__).resolve().parent / ".env"

# Load environment variables
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
elif BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=BACKEND_ENV_PATH)
else:
    load_dotenv()


class Config:
    """App configuration with multi-account failover pool."""

    CLOUDFLARE_MODEL = os.getenv(
        "CLOUDFLARE_MODEL", "@cf/black-forest-labs/flux-1-schnell"
    ).strip()

    # Primary Cloudflare account
    CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

    # Google Gemini API Keys (optional fallback)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "").strip()

    # Pollinations API Key (Priority & Turbo)
    POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()

    # Flask settings
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")

    # Image generation defaults
    DEFAULT_STEPS = int(os.getenv("DEFAULT_STEPS", 4))
    MAX_PROMPT_LENGTH = 2000

    @classmethod
    def get_gemini_keys(cls) -> List[str]:
        """Return list of all configured Gemini API keys."""
        keys = []
        if cls.GEMINI_API_KEY:
            keys.append(cls.GEMINI_API_KEY)
        if cls.GEMINI_API_KEY_2:
            keys.append(cls.GEMINI_API_KEY_2)
        for i in range(3, 10):
            k = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
            if k:
                keys.append(k)
        return keys

    @classmethod
    def get_cloudflare_accounts(cls) -> List[Tuple[str, str]]:
        """Return list of all configured (account_id, api_token) pairs."""
        accounts = []
        # Check primary account
        if cls.CLOUDFLARE_ACCOUNT_ID and cls.CLOUDFLARE_API_TOKEN:
            accounts.append((cls.CLOUDFLARE_ACCOUNT_ID, cls.CLOUDFLARE_API_TOKEN))

        # Check numbered backup accounts (CLOUDFLARE_ACCOUNT_ID_2 ... 10)
        for i in range(2, 20):
            acc_id = os.getenv(f"CLOUDFLARE_ACCOUNT_ID_{i}", "").strip()
            token = os.getenv(f"CLOUDFLARE_API_TOKEN_{i}", "").strip()
            if acc_id and token:
                accounts.append((acc_id, token))

        return accounts

    @classmethod
    def is_configured(cls) -> bool:
        """Check if at least one Cloudflare account or alternative provider is configured."""
        return bool(cls.get_cloudflare_accounts() or cls.get_gemini_keys())
