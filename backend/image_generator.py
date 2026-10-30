"""Unified Image Generator for AI Studio.
Coordinates Cloudflare Workers AI (5-account failover), Google Gemini, and Pollinations FLUX.
Handles prompt enhancement, negative prompts, aspect ratio preservation, user storage, and quota enforcement.
"""

import io
import time
import base64
import logging
from typing import Dict, Any, Tuple, Optional
from PIL import Image
from config import Config
from cloudflare_client import CloudflareAIClient
from storage_manager import storage_manager
from usage_manager import usage_manager

logger = logging.getLogger("ai_studio.image_gen")

# Extended Studio Styles
IMAGE_STYLES = {
    "realistic": "photorealistic, ultra-detailed 8k resolution, natural lighting, professional photography, raw photo style, sharp focus",
    "cinematic": "cinematic still, 35mm movie photography, dramatic volumetric lighting, anamorphic lens, depth of field, blockbuster movie aesthetic",
    "anime": "vibrant Japanese anime aesthetic, sharp clean lines, rich studio animation colors, Makoto Shinkai inspired masterpiece, digital artwork",
    "3d": "3D digital render, Octane render 8k, Unreal Engine 5 visual quality, raytraced lighting, subsurface scattering, stylized 3D model",
    "digital_art": "digital concept art, intricate digital painting, trending on ArtStation, vivid colors, fantasy illustration, masterpiece",
    "fantasy": "high fantasy world, magical ethereal glow, mystical atmosphere, hyper-detailed, Lord of the Rings aesthetic, epic composition",
    "wildlife": "National Geographic wildlife photography, telephoto lens, natural habitat, crisp animal fur details, golden hour lighting, authentic documentary",
}

# Aspect Ratio Framing Directives
ASPECT_PREFIXES = {
    "1:1": "square 1:1 framing, centered focus: ",
    "square": "square 1:1 framing, centered focus: ",
    "16:9": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "landscape": "wide-angle panoramic view, 16:9 cinematic horizontal framing, centered subjects with generous top headroom: ",
    "9:16": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "portrait": "tall 9:16 vertical portrait composition, full length vertical perspective, centered framing: ",
    "4:3": "classic 4:3 photograph composition, balanced framing with proper headroom: ",
}


class StudioImageGenerator:
    """Manages studio image generation with multi-provider failover and user persistence."""

    def __init__(self):
        self.cf_client = CloudflareAIClient()

    def build_studio_prompt(
        self,
        prompt: str,
        style: str = "realistic",
        aspect_ratio: str = "1:1",
        negative_prompt: str = "",
    ) -> str:
        """Construct the prompt incorporating style, aspect ratio framing, and negative avoidance."""
        cleaned_prompt = prompt.strip()
        style_key = style.lower().strip().replace(" ", "_")
        style_desc = IMAGE_STYLES.get(style_key, IMAGE_STYLES["realistic"])
        aspect_prefix = ASPECT_PREFIXES.get(aspect_ratio.lower().strip(), "")

        enhanced = f"{aspect_prefix}{cleaned_prompt}, {style_desc}"
        if negative_prompt and negative_prompt.strip():
            enhanced = f"{enhanced}. Avoid: {negative_prompt.strip()}"

        return enhanced

    def apply_studio_crop(self, raw_bytes: bytes, aspect_ratio: str) -> bytes:
        """
        Crop/format raw square image bytes to requested aspect ratios without decapitation:
        - 1:1: Keep 1024x1024
        - 16:9: Crop to 1024x576 (top trimmed only 12% to preserve heads and crowns)
        - 9:16: Center crop to 576x1024
        - 4:3: Crop to 1024x768 (top trimmed only 15% to preserve headroom)
        """
        aspect = (aspect_ratio or "1:1").lower().strip()
        if aspect in ("1:1", "square", "1/1"):
            return raw_bytes

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                width, height = img.size

                if aspect in ("16:9", "landscape", "16/9", "16-9"):
                    target_height = int(width * 9 / 16)
                    if target_height < height:
                        top = int((height - target_height) * 0.12)
                        img = img.crop((0, top, width, top + target_height))

                elif aspect in ("9:16", "portrait", "9/16", "9-16"):
                    target_width = int(height * 9 / 16)
                    if target_width < width:
                        left = (width - target_width) // 2
                        img = img.crop((left, 0, left + target_width, height))

                elif aspect in ("4:3", "4/3", "4-3"):
                    target_height = int(width * 3 / 4)
                    if target_height < height:
                        top = int((height - target_height) * 0.15)
                        img = img.crop((0, top, width, top + target_height))

                output_io = io.BytesIO()
                img.save(output_io, format="JPEG", quality=98, subsampling=0)
                return output_io.getvalue()
        except Exception as e:
            logger.warning("Studio crop warning: %s", e)
            return raw_bytes

    def generate_image_for_user(
        self,
        user_id: str,
        prompt: str,
        style: str = "realistic",
        aspect_ratio: str = "1:1",
        negative_prompt: str = "",
        steps: int = 8,
        seed: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Full user generation workflow:
        1. Check user quota
        2. Execute generation with provider priority (Cloudflare -> Gemini -> Pollinations)
        3. Save result to user-isolated gallery
        4. Increment user usage
        """
        # 1. Quota Check
        allowed, quota_info = usage_manager.check_quota(user_id, "image")
        if not allowed:
            return False, {
                "error": f"Daily image limit reached ({quota_info['limit']} images/day). Resets at midnight UTC.",
                "code": "QUOTA_EXCEEDED",
                "quota": quota_info,
            }

        # 2. Build Enhanced Prompt
        enhanced_prompt = self.build_studio_prompt(prompt, style, aspect_ratio, negative_prompt)

        # 3. Call multi-provider client with Cloudflare -> Gemini -> Pollinations priority
        success, result = self._dispatch_generation(prompt, enhanced_prompt, style, aspect_ratio, steps, seed)
        if not success:
            return False, result

        # 4. Save to user's personal gallery
        raw_bytes = result.get("raw_bytes")
        if not raw_bytes and "raw_base64" in result:
            raw_bytes = base64.b64decode(result["raw_base64"])

        if raw_bytes:
            media_record = storage_manager.save_media(
                user_id=user_id,
                media_type="image",
                file_bytes=raw_bytes,
                prompt=prompt,
                enhanced_prompt=enhanced_prompt,
                style=style,
                aspect_ratio=aspect_ratio,
                provider=result.get("provider", "ORAI Engine"),
                model=result.get("model", ""),
            )
            result["media_record"] = media_record
            result["media_url"] = media_record["url"]

        # 5. Record usage
        usage_manager.record_usage(
            user_id=user_id,
            media_type="image",
            provider=result.get("provider", ""),
            model=result.get("model", ""),
            success=True,
        )

        return True, result

    def _dispatch_generation(
        self,
        original_prompt: str,
        enhanced_prompt: str,
        style: str,
        aspect_ratio: str,
        steps: int,
        seed: Optional[int],
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Provider Priority Chain:
        1. Cloudflare Workers AI Pool (5 Accounts Failover)
        2. Google Gemini Image API
        3. Pollinations API (Priority Turbo FLUX)
        """
        clamped_steps = max(4, min(int(steps or 8), 8))
        accounts = Config.get_cloudflare_accounts()

        # =============================================================
        # 1. Cloudflare Workers AI Pool (Primary)
        # =============================================================
        if accounts:
            num_accounts = len(accounts)
            logger.info("Image Priority 1: Cloudflare Pool (%d accounts)...", num_accounts)
            for attempt in range(num_accounts):
                acc_idx = (self.cf_client.current_account_idx + attempt) % num_accounts
                account_id, api_token = accounts[acc_idx]

                success, result = self.cf_client._call_cloudflare(
                    account_id, api_token, enhanced_prompt, clamped_steps, seed
                )

                if success:
                    self.cf_client.current_account_idx = acc_idx
                    raw_bytes = result["raw_bytes"]
                    cropped_bytes = self.apply_studio_crop(raw_bytes, aspect_ratio)
                    b64_str = base64.b64encode(cropped_bytes).decode("utf-8")
                    return True, {
                        "image": f"data:image/jpeg;base64,{b64_str}",
                        "raw_base64": b64_str,
                        "raw_bytes": cropped_bytes,
                        "original_prompt": original_prompt,
                        "enhanced_prompt": enhanced_prompt,
                        "style": style,
                        "aspect_ratio": aspect_ratio,
                        "steps": clamped_steps,
                        "provider": f"Cloudflare Workers AI (Account #{acc_idx + 1})",
                        "model": self.cf_client.model,
                    }

                if result.get("code") in ("RATE_LIMIT_EXCEEDED", "INVALID_TOKEN", "NOT_FOUND"):
                    logger.warning("Cloudflare #%d limited (%s). Trying next...", acc_idx + 1, result.get("code"))
                    continue

        # =============================================================
        # 2. Google Gemini Image API (Fallback)
        # =============================================================
        gemini_keys = Config.get_gemini_keys()
        if gemini_keys:
            logger.info("Image Priority 2: Google Gemini...")
            for g_idx, g_key in enumerate(gemini_keys):
                success, result = self.cf_client._call_gemini(g_key, enhanced_prompt, aspect_ratio)
                if success:
                    raw_bytes = result["raw_bytes"]
                    cropped_bytes = self.apply_studio_crop(raw_bytes, aspect_ratio)
                    b64_str = base64.b64encode(cropped_bytes).decode("utf-8")
                    return True, {
                        "image": f"data:image/jpeg;base64,{b64_str}",
                        "raw_base64": b64_str,
                        "raw_bytes": cropped_bytes,
                        "original_prompt": original_prompt,
                        "enhanced_prompt": enhanced_prompt,
                        "style": style,
                        "aspect_ratio": aspect_ratio,
                        "steps": clamped_steps,
                        "provider": f"Google Gemini (Key #{g_idx + 1})",
                        "model": result.get("model", "gemini-image"),
                    }

        # =============================================================
        # 3. Pollinations API (Universal Turbo Safety Net)
        # =============================================================
        logger.info("Image Priority 3: Pollinations FLUX...")
        success, result = self.cf_client._call_pollinations(enhanced_prompt, aspect_ratio, seed)
        if success:
            raw_bytes = result["raw_bytes"]
            final_bytes = raw_bytes if result.get("native_ratio") else self.apply_studio_crop(raw_bytes, aspect_ratio)
            b64_str = base64.b64encode(final_bytes).decode("utf-8")
            provider_label = "Pollinations FLUX (Priority API)" if Config.POLLINATIONS_API_KEY else "Pollinations FLUX"
            return True, {
                "image": f"data:image/jpeg;base64,{b64_str}",
                "raw_base64": b64_str,
                "raw_bytes": final_bytes,
                "original_prompt": original_prompt,
                "enhanced_prompt": enhanced_prompt,
                "style": style,
                "aspect_ratio": aspect_ratio,
                "steps": clamped_steps,
                "provider": provider_label,
                "model": "FLUX.1 [Native High-Res]",
            }

        return False, {
            "error": "All AI generation providers are temporarily unavailable. Please retry in a moment.",
            "code": "ALL_PROVIDERS_UNAVAILABLE",
        }


image_generator = StudioImageGenerator()
