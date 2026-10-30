"""Storage Manager for AI Studio.
Handles media storage (images/videos) and metadata per user.
Supports Firestore and local resilient JSON storage.
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import Config
from firebase_service import get_firestore_client
import logging

logger = logging.getLogger("ai_studio.storage")


class StorageManager:
    """Manages file storage and user galleries with user isolation."""

    def __init__(self):
        self.upload_dir = Config.UPLOAD_DIR
        self.images_dir = Config.MEDIA_IMAGES_DIR
        self.videos_dir = Config.MEDIA_VIDEOS_DIR
        self.meta_dir = self.upload_dir / "metadata"

        # Ensure directories exist
        for d in [self.upload_dir, self.images_dir, self.videos_dir, self.meta_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _get_user_meta_file(self, user_id: str) -> Path:
        safe_uid = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "anon"
        return self.meta_dir / f"{safe_uid}.json"

    def _read_user_gallery_local(self, user_id: str) -> List[Dict[str, Any]]:
        meta_file = self._get_user_meta_file(user_id)
        if not meta_file.exists():
            return []
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Error reading user gallery: %s", e)
            return []

    def _write_user_gallery_local(self, user_id: str, items: List[Dict[str, Any]]) -> None:
        meta_file = self._get_user_meta_file(user_id)
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Error writing user gallery: %s", e)

    def save_media(
        self,
        user_id: str,
        media_type: str,  # "image" or "video"
        file_bytes: bytes,
        prompt: str,
        enhanced_prompt: str = "",
        style: str = "",
        aspect_ratio: str = "1:1",
        provider: str = "",
        model: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Save a generated image or video file and index its metadata."""
        media_id = f"med_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        extension = "mp4" if media_type == "video" else "jpg"
        filename = f"{media_id}.{extension}"

        # User directory
        safe_uid = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "anon"
        target_dir = (self.videos_dir if media_type == "video" else self.images_dir) / safe_uid
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename

        # Write file to disk
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        media_url = f"/api/media/{media_type}/{safe_uid}/{filename}"

        record = {
            "id": media_id,
            "user_id": user_id,
            "type": media_type,
            "filename": filename,
            "url": media_url,
            "prompt": prompt,
            "enhanced_prompt": enhanced_prompt or prompt,
            "style": style,
            "aspect_ratio": aspect_ratio,
            "provider": provider,
            "model": model,
            "file_size": len(file_bytes),
            "created_at": time.time(),
            "created_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "extra": extra or {},
        }

        # 1. Save to local user index
        items = self._read_user_gallery_local(user_id)
        items.insert(0, record)
        self._write_user_gallery_local(user_id, items)

        # 2. Try Firestore if available
        db = get_firestore_client()
        if db:
            try:
                db.collection("users").document(user_id).collection("gallery").document(media_id).set(record)
            except Exception as fe:
                logger.debug("Firestore gallery write note: %s", fe)

        return record

    def get_user_gallery(self, user_id: str, media_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve the isolated gallery for a specific authenticated user."""
        items = self._read_user_gallery_local(user_id)
        if media_type:
            items = [item for item in items if item.get("type") == media_type]
        return items

    def delete_user_media(self, user_id: str, media_id: str) -> bool:
        """Delete an item from a user's gallery and remove the file."""
        items = self._read_user_gallery_local(user_id)
        found_item = None
        new_items = []
        for it in items:
            if it.get("id") == media_id:
                found_item = it
            else:
                new_items.append(it)

        if not found_item:
            return False

        self._write_user_gallery_local(user_id, new_items)

        # Remove local file
        try:
            safe_uid = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "anon"
            m_type = found_item.get("type", "image")
            f_name = found_item.get("filename", "")
            target_dir = (self.videos_dir if m_type == "video" else self.images_dir) / safe_uid
            target_file = target_dir / f_name
            if target_file.exists():
                target_file.unlink()
        except Exception as e:
            logger.warning("Could not delete physical file: %s", e)

        # Remove from Firestore
        db = get_firestore_client()
        if db:
            try:
                db.collection("users").document(user_id).collection("gallery").document(media_id).delete()
            except Exception:
                pass

        return True


storage_manager = StorageManager()
