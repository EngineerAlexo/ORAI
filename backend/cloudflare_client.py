"""Multi-Provider AI Image Engine for ORAI.
Supports:
1. Multi-Account Cloudflare Workers AI (FLUX.1 Schnell) with auto-failover & rotation.
2. Google Gemini / Imagen 3 fallback (if GEMINI_API_KEY is configured).
3. Pollinations.ai FLUX (unlimited emergency safety net fallback).
"""

import io
import base64
import logging
import urllib.parse
from typing import Dict, Any, Tuple, Optional, List
from PIL import Image
import requests
from config import Config

logger = logging.getLogger("orai.engine")

# Style prompt modifiers
STYLE_MODIFIERS = {
    "realistic": "photorealistic, ultra-detailed 8k resolution, natural lighting, professional photography, raw photo style, sharp focus",
    "anime": "vibrant Japanese anime aesthetic, sharp clean lines, rich studio animation colors, Makoto Shinkai inspired masterpiece, digital artwork",
    "cinematic": "cinematic still, 35mm movie photography, dramatic volumetric lighting, anamorphic lens, depth of field, blockbuster movie aesthetic",
    "3d": "3D digital render, Octane render 8k, Unreal Engine 5 visual quality, raytraced lighting, subsurface scattering, stylized 3D model",
}

# Aspect ratio framing prefixes (prepended at start so FLUX compositions retain proper headroom and perspective)
ASPECT_RATIO_PREFIX = {
    "landscape": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "16:9": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "16/9": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "16-9": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "portrait": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "9:16": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "9/16": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "9-16": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "square": "square 1:1 framing, centered focus: ",
    "1:1": "square 1:1 framing, centered focus: ",
    "1/1": "square 1:1 framing, centered focus: ",
}


class CloudflareAIClient:
    """Multi-account and multi-provider image generation client."""

    def __init__(self, accounts: Optional[List[Tuple[str, str]]] = None, model: Optional[str] = None):
        self.accounts = accounts or Config.get_cloudflare_accounts()
        self.model = (model or Config.CLOUDFLARE_MODEL).strip()
        self.current_account_idx = 0

    @property
    def total_accounts(self) -> int:
        return len(self.accounts)

    def build_enhanced_prompt(self, user_prompt: str, style: str = "realistic", aspect_ratio: str = "1:1") -> str:
        """Combine user prompt with style and framing enhancements."""
        cleaned_prompt = user_prompt.strip()
        style_modifier = STYLE_MODIFIERS.get(style.lower().strip(), "")
        aspect_prefix = ASPECT_RATIO_PREFIX.get(aspect_ratio.lower().strip(), "")

        # Framing prefix goes first so FLUX composes the wide/portrait shot properly
        enhanced = f"{aspect_prefix}{cleaned_prompt}"
        if style_modifier:
            enhanced = f"{enhanced}, {style_modifier}"

        return enhanced

    def apply_aspect_ratio(self, raw_bytes: bytes, aspect_ratio: str) -> bytes:
        """
        Crop/format raw image bytes to exact requested aspect ratio:
        - '16:9' / 'landscape': Crop 1024x1024 to 1024x576 preserving top headroom (Rule of Thirds)
        - '9:16' / 'portrait': Center-crop 1024x1024 to 576x1024
        - '1:1' / 'square': Keep 1024x1024 as is
        """
        aspect = (aspect_ratio or "1:1").lower().strip()
        if aspect in ("square", "1:1", "1/1"):
            return raw_bytes

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                width, height = img.size
                
                if aspect in ("landscape", "16:9", "16/9", "16-9"):
                    target_height = int(width * 9 / 16)
                    if target_height < height:
                        # Rule of Thirds headroom preservation:
                        # Standard 50/50 center crop chops off heads/hair.
                        # We trim only ~10-12% from the top so heads, hair, and crowns stay 100% visible,
                        # and trim the remainder from the bottom.
                        top = int((height - target_height) * 0.12)
                        img = img.crop((0, top, width, top + target_height))
                        
                elif aspect in ("portrait", "9:16", "9/16", "9-16"):
                    target_width = int(height * 9 / 16)
                    if target_width < width:
                        left = (width - target_width) // 2
                        img = img.crop((left, 0, left + target_width, height))

                output_io = io.BytesIO()
                img.save(output_io, format="JPEG", quality=98, subsampling=0)
                return output_io.getvalue()
        except Exception as err:
            logger.warning("Could not apply aspect ratio crop: %s", err)
            return raw_bytes

    def generate_image(
        self,
        prompt: str,
        style: str = "realistic",
        aspect_ratio: str = "square",
        steps: int = 4,
        seed: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Generate an image using the Multi-Provider failover chain with strict priority:
        1. Google Gemini (Priority 1: Checks all configured Gemini keys)
        2. Pollinations FLUX (Priority 2: Native aspect ratio, priority API key, enhance=true)
        3. Cloudflare Workers AI (Priority 3: Cycles through all 5 accounts on rate limit 429)
        """
        if not prompt or not prompt.strip():
            return False, {
                "error": "A prompt is required to generate an image.",
                "code": "EMPTY_PROMPT",
            }

        enhanced_prompt = self.build_enhanced_prompt(prompt, style, aspect_ratio)
        clamped_steps = max(4, min(int(steps or 8), 8))

        # Re-fetch latest accounts in case .env was refreshed
        self.accounts = Config.get_cloudflare_accounts()

        # =============================================================
        # PRIORITY 1: Google Gemini (If keys are configured)
        # =============================================================
        gemini_keys = Config.get_gemini_keys()
        if gemini_keys:
            logger.info("Priority 1: Attempting Google Gemini Image...")
            for g_idx, g_key in enumerate(gemini_keys):
                success, result = self._call_gemini(g_key, enhanced_prompt, aspect_ratio)
                if success:
                    raw_bytes = result["raw_bytes"]
                    cropped_bytes = self.apply_aspect_ratio(raw_bytes, aspect_ratio)
                    b64_str = base64.b64encode(cropped_bytes).decode("utf-8")
                    return True, {
                        "image": f"data:image/jpeg;base64,{b64_str}",
                        "raw_base64": b64_str,
                        "original_prompt": prompt,
                        "enhanced_prompt": enhanced_prompt,
                        "style": style,
                        "aspect_ratio": aspect_ratio,
                        "steps": clamped_steps,
                        "provider": f"Google Gemini (Key #{g_idx + 1})",
                        "model": result.get("model", "gemini-image"),
                    }
                else:
                    logger.warning(
                        "Gemini Key #%d unavailable or quota reached. Switching to next provider...",
                        g_idx + 1
                    )

        # =============================================================
        # PRIORITY 2: Pollinations.ai FLUX (High-speed authenticated tier)
        # =============================================================
        logger.info("Priority 2: Attempting Pollinations FLUX Engine...")
        success, result = self._call_pollinations(enhanced_prompt, aspect_ratio, seed)
        if success:
            raw_bytes = result["raw_bytes"]
            final_bytes = raw_bytes if result.get("native_ratio") else self.apply_aspect_ratio(raw_bytes, aspect_ratio)
            b64_str = base64.b64encode(final_bytes).decode("utf-8")
            provider_label = "Pollinations FLUX (Priority API)" if Config.POLLINATIONS_API_KEY else "Pollinations FLUX"
            return True, {
                "image": f"data:image/jpeg;base64,{b64_str}",
                "raw_base64": b64_str,
                "original_prompt": prompt,
                "enhanced_prompt": enhanced_prompt,
                "style": style,
                "aspect_ratio": aspect_ratio,
                "steps": clamped_steps,
                "provider": provider_label,
                "model": "FLUX.1 [Native High-Res]",
            }
        else:
            logger.warning("Pollinations FLUX failed. Switching to Cloudflare Pool...")

        # =============================================================
        # PRIORITY 3: Cloudflare Workers AI Pool (5 Accounts Auto-Failover)
        # =============================================================
        if self.accounts:
            num_accounts = len(self.accounts)
            logger.info("Priority 3: Attempting Cloudflare Pool (%d accounts)...", num_accounts)
            for attempt in range(num_accounts):
                # Pick account in rotation
                acc_idx = (self.current_account_idx + attempt) % num_accounts
                account_id, api_token = self.accounts[acc_idx]
                
                logger.info(
                    "Attempting Cloudflare Account #%d/%d (%s...)",
                    acc_idx + 1, num_accounts, account_id[:6]
                )

                success, result = self._call_cloudflare(
                    account_id, api_token, enhanced_prompt, clamped_steps, seed
                )

                if success:
                    # Remember this working account
                    self.current_account_idx = acc_idx
                    raw_bytes = result["raw_bytes"]
                    cropped_bytes = self.apply_aspect_ratio(raw_bytes, aspect_ratio)
                    b64_str = base64.b64encode(cropped_bytes).decode("utf-8")
                    
                    return True, {
                        "image": f"data:image/jpeg;base64,{b64_str}",
                        "raw_base64": b64_str,
                        "original_prompt": prompt,
                        "enhanced_prompt": enhanced_prompt,
                        "style": style,
                        "aspect_ratio": aspect_ratio,
                        "steps": clamped_steps,
                        "provider": f"Cloudflare Workers AI (Account #{acc_idx + 1})",
                        "model": self.model,
                    }

                # If rate-limited (429) or invalid, auto-switch to next account
                if result.get("code") in ("RATE_LIMIT_EXCEEDED", "INVALID_TOKEN", "NOT_FOUND"):
                    next_acc = ((acc_idx + 1) % num_accounts) + 1
                    logger.warning(
                        "Cloudflare Account #%d reached limitation (%s). Automatically switching to Account #%d...",
                        acc_idx + 1, result.get("code"), next_acc
                    )
                    continue
                else:
                    logger.warning("Cloudflare error on account #%d: %s", acc_idx + 1, result.get("error"))

        return False, {
            "error": "All AI generation providers are temporarily unavailable. Please retry in a moment.",
            "code": "ALL_PROVIDERS_UNAVAILABLE",
        }

    def _call_cloudflare(
        self, account_id: str, api_token: str, enhanced_prompt: str, steps: int, seed: Optional[int]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Call a specific Cloudflare Workers AI account."""
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{self.model}"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }
        payload = {"prompt": enhanced_prompt, "steps": steps}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=85)
        except Exception as exc:
            return False, {"error": str(exc), "code": "CONNECTION_ERROR"}

        if res.status_code == 429:
            return False, {"error": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED"}
        if res.status_code == 401:
            return False, {"error": "Invalid API token", "code": "INVALID_TOKEN"}
        if res.status_code == 404:
            return False, {"error": "Not found", "code": "NOT_FOUND"}
        if not res.ok:
            return False, {"error": res.text[:150], "code": f"HTTP_{res.status_code}"}

        # Extract image bytes
        content_type = res.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                data = res.json()
                b64_str = None
                if isinstance(data, dict):
                    if "result" in data and isinstance(data["result"], dict):
                        b64_str = data["result"].get("image")
                    elif "image" in data:
                        b64_str = data.get("image")
                if b64_str:
                    return True, {"raw_bytes": base64.b64decode(b64_str)}
            except Exception as e:
                logger.error("JSON parse error: %s", e)

        if res.content:
            return True, {"raw_bytes": res.content}

        return False, {"error": "Empty image response", "code": "EMPTY_RESPONSE"}

    def _call_gemini(self, api_key: str, prompt: str, aspect_ratio: str) -> Tuple[bool, Dict[str, Any]]:
        """Call Google Gemini Image Generation endpoint."""
        # 1. Try Gemini 2.5 Flash Image endpoint
        flash_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
        flash_payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        try:
            res = requests.post(flash_url, json=flash_payload, timeout=60)
            if res.ok:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        inline_data = part.get("inlineData", {})
                        b64_str = inline_data.get("data")
                        if b64_str:
                            return True, {
                                "raw_bytes": base64.b64decode(b64_str),
                                "model": "gemini-2.5-flash-image",
                            }
            elif res.status_code == 429:
                logger.warning("Gemini Image quota exceeded (free-tier limit: 0, requires billing).")
        except Exception as e:
            logger.warning("Gemini 2.5 Flash Image call error: %s", e)

        # 2. Try Imagen 3 predict endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        aspect = "1:1"
        if aspect_ratio in ("landscape", "16:9", "16-9"):
            aspect = "16:9"
        elif aspect_ratio in ("portrait", "9:16", "9-16"):
            aspect = "9:16"

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": aspect},
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.ok:
                data = res.json()
                predictions = data.get("predictions", [])
                if predictions and "bytesBase64Encoded" in predictions[0]:
                    raw_b64 = predictions[0]["bytesBase64Encoded"]
                    return True, {
                        "raw_bytes": base64.b64decode(raw_b64),
                        "model": "imagen-3.0-generate-002",
                    }
        except Exception as e:
            logger.warning("Gemini Imagen 3 call error: %s", e)

        return False, {"error": "Gemini generation failed (requires billing on Google AI Studio)", "code": "GEMINI_QUOTA"}

    def _call_pollinations(
        self, prompt: str, aspect_ratio: str, seed: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Call Pollinations.ai FLUX (supports native high-res, enhance=true, and priority API key)."""
        aspect = (aspect_ratio or "1:1").lower().strip()
        width, height = 1024, 1024
        if aspect in ("landscape", "16:9", "16-9", "16/9"):
            width, height = 1024, 576
        elif aspect in ("portrait", "9:16", "9-16", "9/16"):
            width, height = 576, 1024

        import random
        gen_seed = seed if seed is not None else random.randint(1000, 9999999)
        encoded = urllib.parse.quote_plus(prompt[:1000])
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&model=flux&nologo=true&enhance=true&seed={gen_seed}"
        )

        headers = {}
        if Config.POLLINATIONS_API_KEY:
            headers["Authorization"] = f"Bearer {Config.POLLINATIONS_API_KEY}"

        try:
            res = requests.get(url, headers=headers, timeout=50)
            if res.ok and len(res.content) > 1000:
                return True, {"raw_bytes": res.content, "native_ratio": True}
        except Exception as e:
            logger.warning("Pollinations call error: %s", e)

        return False, {"error": "Pollinations generation failed", "code": "POLLINATIONS_ERROR"}
