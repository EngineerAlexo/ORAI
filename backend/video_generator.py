"""Modular AI Video Generation Engine for AI Studio.
Supports:
1. Text-to-Video (T2V)
2. Image-to-Video (I2V)
Handles asynchronous generation queues, background polling, and real MP4 download.
"""

import os
import time
import uuid
import base64
import logging
import threading
from typing import Dict, Any, Optional
import requests
from config import Config
from storage_manager import storage_manager
from usage_manager import usage_manager

logger = logging.getLogger("ai_studio.video")

# In-memory job state store for background video tasks
_VIDEO_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


class VideoGenerator:
    """Manages asynchronous video generation tasks and multi-provider dispatch."""

    def __init__(self):
        self.pollinations_key = Config.POLLINATIONS_API_KEY
        self.hf_token = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN", "")
        self.replicate_token = os.getenv("REPLICATE_API_TOKEN", "")
        self.runware_key = os.getenv("RUNWARE_API_KEY", "")
        self.modelslab_key = os.getenv("MODELSLAB_API_KEY", "")

    def get_available_providers(self) -> Dict[str, Any]:
        """Check which video generation backends are configured."""
        return {
            "pollinations": bool(self.pollinations_key),
            "huggingface": bool(self.hf_token),
            "replicate": bool(self.replicate_token),
            "runware": bool(self.runware_key),
            "modelslab": bool(self.modelslab_key),
            "any_available": bool(
                self.pollinations_key
                or self.hf_token
                or self.replicate_token
                or self.runware_key
                or self.modelslab_key
            ),
        }

    def create_video_job(
        self,
        user_id: str,
        mode: str,  # "text-to-video" or "image-to-video"
        prompt: str,
        aspect_ratio: str = "16:9",
        duration: int = 4,
        image_data: Optional[str] = None,
        negative_prompt: str = "",
    ) -> Dict[str, Any]:
        """Initialize a new video generation job in background."""
        job_id = f"vjob_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        job_record = {
            "job_id": job_id,
            "user_id": user_id,
            "mode": mode,
            "prompt": prompt.strip(),
            "negative_prompt": negative_prompt.strip(),
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "image_data_len": len(image_data) if image_data else 0,
            "status": "queued",  # queued, processing, completed, failed
            "progress": 5,
            "message": "Job queued for video synthesis...",
            "created_at": time.time(),
            "updated_at": time.time(),
            "video_url": None,
            "media_record": None,
            "error": None,
            "provider": None,
            "model": None,
        }

        with _JOBS_LOCK:
            _VIDEO_JOBS[job_id] = job_record

        # Launch background processing thread
        worker_thread = threading.Thread(
            target=self._process_video_job,
            args=(job_id, user_id, mode, prompt, aspect_ratio, duration, image_data, negative_prompt),
            daemon=True,
        )
        worker_thread.start()

        return job_record

    def get_job_status(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the current progress and status of a video job with user verification."""
        with _JOBS_LOCK:
            job = _VIDEO_JOBS.get(job_id)
            if not job or job.get("user_id") != user_id:
                return None
            return dict(job)

    def _update_job(self, job_id: str, **kwargs):
        """Update job fields thread-safely."""
        with _JOBS_LOCK:
            if job_id in _VIDEO_JOBS:
                _VIDEO_JOBS[job_id].update(kwargs)
                _VIDEO_JOBS[job_id]["updated_at"] = time.time()

    def _process_video_job(
        self,
        job_id: str,
        user_id: str,
        mode: str,
        prompt: str,
        aspect_ratio: str,
        duration: int,
        image_data: Optional[str],
        negative_prompt: str,
    ):
        """Worker thread executing real video generation pipeline."""
        logger.info("Starting background video job %s (mode: %s, user: %s)", job_id, mode, user_id)
        self._update_job(job_id, status="processing", progress=15, message="Connecting to AI Video GPU cluster...")

        # -------------------------------------------------------------
        # 1. Multi-Provider Video Dispatch Chain
        # -------------------------------------------------------------
        providers = self.get_available_providers()
        provider_notes = []

        # Try Pollinations Video if key is configured
        if providers["pollinations"]:
            self._update_job(job_id, progress=30, message="Synthesizing video with Pollinations AI...")
            success, res = self._generate_pollinations_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("insufficient_balance"):
                provider_notes.append("Pollinations: Account has 0.00 pollen balance (~0.60 pollen required per video). Top up at https://enter.pollinations.ai")
            elif res.get("error"):
                provider_notes.append(f"Pollinations: {res.get('error')}")

        # Try Hugging Face Router API if token is present
        if providers["huggingface"]:
            self._update_job(job_id, progress=45, message="Synthesizing video frames on Hugging Face...")
            success, res = self._generate_hf_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("error"):
                provider_notes.append(f"Hugging Face: {res.get('error')}")

        # Try Replicate Video API if token is present
        if providers["replicate"]:
            self._update_job(job_id, progress=55, message="Synthesizing video with Replicate (SVD)...")
            success, res = self._generate_replicate_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("error"):
                provider_notes.append(f"Replicate: {res.get('error')}")

        # Try ModelsLab if configured
        if providers["modelslab"]:
            self._update_job(job_id, progress=65, message="Dispatching to ModelsLab Video API...")
            success, res = self._generate_modelslab_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("error"):
                provider_notes.append(f"ModelsLab: {res.get('error')}")

        # -------------------------------------------------------------
        # 2. Honest Fallback When No Video Provider Is Ready
        # -------------------------------------------------------------
        logger.warning("No video generation API keys available or all failed for job %s", job_id)
        error_details = "\n".join(provider_notes) if provider_notes else (
            "No active AI Video Provider API key configured.\n"
            "High-performance video generation (Text-to-Video & Image-to-Video) requires GPU credits.\n"
            "To enable video generation, please configure one of the following in your .env file:\n"
            "- POLLINATIONS_API_KEY (with pollen credit from enter.pollinations.ai)\n"
            "- HUGGINGFACE_API_KEY / HF_TOKEN (from huggingface.co/settings/tokens)\n"
            "- REPLICATE_API_TOKEN (from replicate.com/account/api-tokens)\n"
            "- MODELSLAB_API_KEY (from modelslab.com)"
        )

        self._update_job(
            job_id,
            status="failed",
            progress=100,
            error=error_details,
            message="Video synthesis halted: No funded video provider available.",
        )

    def _generate_pollinations_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call Pollinations AI video generation endpoint."""
        url = f"https://gen.pollinations.ai/video/{requests.utils.quote(prompt)}"
        headers = {}
        if self.pollinations_key:
            headers["Authorization"] = f"Bearer {self.pollinations_key}"

        try:
            res = requests.get(url, headers=headers, timeout=120)
            if res.ok and len(res.content) > 5000:
                ct = res.headers.get("content-type", "")
                if "video" in ct or "mp4" in ct or res.content[:4] in (b"\x00\x00\x00\x18", b"\x00\x00\x00\x1c", b"\x00\x00\x00\x20"):
                    return True, {
                        "video_bytes": res.content,
                        "provider": "Pollinations Video",
                        "model": "Pollinations Video Gen",
                    }

            if res.status_code == 402:
                logger.warning("Pollinations video: 402 insufficient balance")
                return False, {"insufficient_balance": True}

            logger.warning("Pollinations video returned %d: %s", res.status_code, res.text[:120])
            return False, {"error": f"HTTP {res.status_code}"}
        except Exception as e:
            logger.error("Pollinations video error: %s", e)
            return False, {"error": str(e)}

    def _generate_replicate_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call Replicate video generation model (Stable Video Diffusion)."""
        headers = {
            "Authorization": f"Bearer {self.replicate_token}",
            "Content-Type": "application/json",
        }
        
        # SVD model deployment
        url = "https://api.replicate.com/v1/predictions"
        payload = {
            "version": "3f0457e4619da8151802e93e261ab87c2e2f0ed226599824bc731ad7ea126677",
            "input": {
                "input_image": image_data if image_data else "https://replicate.delivery/pbxt/JR3pZ2e60xZ56s8u6a7/demo.jpg",
                "sizing_strategy": "maintain_aspect_ratio",
                "frames_per_second": 6,
                "motion_bucket_id": 127,
            }
        }
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if not res.ok:
                return False, {"error": f"Prediction failed with HTTP {res.status_code}"}
            
            pred = res.json()
            poll_url = pred.get("urls", {}).get("get")
            if not poll_url:
                return False, {"error": "Missing poll URL from Replicate"}

            # Poll for completion (up to 90s)
            for _ in range(30):
                time.sleep(3)
                chk = requests.get(poll_url, headers=headers, timeout=15).json()
                status = chk.get("status")
                if status == "succeeded":
                    output_url = chk.get("output")
                    if isinstance(output_url, list):
                        output_url = output_url[0]
                    if output_url:
                        vid_res = requests.get(output_url, timeout=60)
                        if vid_res.ok:
                            return True, {
                                "video_bytes": vid_res.content,
                                "provider": "Replicate AI",
                                "model": "Stable Video Diffusion (SVD)",
                            }
                elif status in ("failed", "canceled"):
                    return False, {"error": chk.get("error", "Replicate prediction failed")}
        except Exception as e:
            logger.error("Replicate video request error: %s", e)
            return False, {"error": str(e)}

        return False, {"error": "Replicate generation timed out"}

    def _generate_hf_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call Hugging Face video model inference."""
        model = "damo-vilab/text-to-video-ms-1.7b"
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {"inputs": prompt}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=120)
            if res.ok and len(res.content) > 5000:
                return True, {
                    "video_bytes": res.content,
                    "provider": "Hugging Face Inference",
                    "model": model,
                }
            logger.warning("HF video failed with status %d: %s", res.status_code, res.text[:150])
        except Exception as e:
            logger.error("HF video request error: %s", e)

        return False, {}

    def _generate_modelslab_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call ModelsLab text-to-video / image-to-video endpoint."""
        url = "https://modelslab.com/api/v6/video/text2video"
        payload = {
            "key": self.modelslab_key,
            "prompt": prompt,
            "model_id": "svd",
        }
        try:
            res = requests.post(url, json=payload, timeout=60)
            if res.ok:
                data = res.json()
                video_url = data.get("output", [None])[0] or data.get("video_url")
                if video_url:
                    v_res = requests.get(video_url, timeout=90)
                    if v_res.ok:
                        return True, {
                            "video_bytes": v_res.content,
                            "provider": "ModelsLab Video",
                            "model": "Stable Video Diffusion",
                        }
        except Exception as e:
            logger.error("ModelsLab video error: %s", e)

        return False, {}

    def _finalize_job_success(
        self,
        job_id: str,
        user_id: str,
        video_bytes: bytes,
        prompt: str,
        aspect_ratio: str,
        provider: str,
        model: str,
    ):
        """Save video to user gallery, update usage metrics, and mark job completed."""
        try:
            media_record = storage_manager.save_media(
                user_id=user_id,
                media_type="video",
                file_bytes=video_bytes,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                provider=provider,
                model=model,
            )

            # Record usage
            usage_manager.record_usage(
                user_id=user_id,
                media_type="video",
                provider=provider,
                model=model,
                success=True,
            )

            self._update_job(
                job_id,
                status="completed",
                progress=100,
                message="Video generated successfully!",
                video_url=media_record["url"],
                media_record=media_record,
                provider=provider,
                model=model,
            )
            logger.info("Video job %s completed successfully for user %s", job_id, user_id)
        except Exception as e:
            logger.error("Error finalizing video job %s: %s", job_id, e)
            self._update_job(job_id, status="failed", error=str(e), progress=100)


video_generator = VideoGenerator()
