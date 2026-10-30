"""Usage Manager for AI Studio.
Enforces daily generation quotas per authenticated user and tracks lifetime usage statistics.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from config import Config
from firebase_service import get_firestore_client
import logging

logger = logging.getLogger("ai_studio.usage")


class UsageManager:
    """Tracks and enforces daily limits per user."""

    def __init__(self):
        self.stats_dir = Config.UPLOAD_DIR / "usage_stats"
        self.stats_dir.mkdir(parents=True, exist_ok=True)

    def _today_str(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _get_user_file(self, user_id: str) -> Path:
        safe_uid = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "anon"
        return self.stats_dir / f"{safe_uid}.json"

    def _get_user_record(self, user_id: str) -> Dict[str, Any]:
        f = self._get_user_file(user_id)
        if f.exists():
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                pass
        return {
            "user_id": user_id,
            "total_images": 0,
            "total_videos": 0,
            "daily": {},
            "history": [],
        }

    def _save_user_record(self, user_id: str, data: Dict[str, Any]) -> None:
        f = self._get_user_file(user_id)
        try:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
        except Exception as e:
            logger.error("Error saving usage record: %s", e)

    def check_quota(self, user_id: str, media_type: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if user has remaining quota for the day.
        Returns: (allowed: bool, details: dict)
        """
        today = self._today_str()
        rec = self._get_user_record(user_id)
        daily_stats = rec.get("daily", {}).get(today, {"images": 0, "videos": 0})

        limit = Config.DAILY_IMAGE_LIMIT if media_type == "image" else Config.DAILY_VIDEO_LIMIT
        current_used = daily_stats.get("images" if media_type == "image" else "videos", 0)

        if current_used >= limit:
            return False, {
                "allowed": False,
                "current_used": current_used,
                "limit": limit,
                "remaining": 0,
                "media_type": media_type,
                "reset_time": "Midnight UTC",
            }

        return True, {
            "allowed": True,
            "current_used": current_used,
            "limit": limit,
            "remaining": limit - current_used,
            "media_type": media_type,
        }

    def record_usage(
        self,
        user_id: str,
        media_type: str,
        provider: str = "",
        model: str = "",
        success: bool = True,
    ) -> None:
        """Increment daily and lifetime count upon successful generation."""
        if not success:
            return

        today = self._today_str()
        rec = self._get_user_record(user_id)

        if "daily" not in rec:
            rec["daily"] = {}
        if today not in rec["daily"]:
            rec["daily"][today] = {"images": 0, "videos": 0}

        if media_type == "image":
            rec["total_images"] = rec.get("total_images", 0) + 1
            rec["daily"][today]["images"] = rec["daily"][today].get("images", 0) + 1
        elif media_type == "video":
            rec["total_videos"] = rec.get("total_videos", 0) + 1
            rec["daily"][today]["videos"] = rec["daily"][today].get("videos", 0) + 1

        self._save_user_record(user_id, rec)

        # Sync with Firestore
        db = get_firestore_client()
        if db:
            try:
                user_ref = db.collection("users").document(user_id)
                user_ref.set({
                    "total_images": rec["total_images"],
                    "total_videos": rec["total_videos"],
                    "last_active": time.time(),
                }, merge=True)
            except Exception:
                pass

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Return usage overview for user profile."""
        today = self._today_str()
        rec = self._get_user_record(user_id)
        daily_stats = rec.get("daily", {}).get(today, {"images": 0, "videos": 0})

        images_used = daily_stats.get("images", 0)
        videos_used = daily_stats.get("videos", 0)

        return {
            "total_images": rec.get("total_images", 0),
            "total_videos": rec.get("total_videos", 0),
            "today_images": images_used,
            "today_videos": videos_used,
            "image_limit": Config.DAILY_IMAGE_LIMIT,
            "video_limit": Config.DAILY_VIDEO_LIMIT,
            "image_remaining": max(0, Config.DAILY_IMAGE_LIMIT - images_used),
            "video_remaining": max(0, Config.DAILY_VIDEO_LIMIT - videos_used),
        }


usage_manager = UsageManager()
