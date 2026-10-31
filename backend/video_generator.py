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

    def _refresh_env(self):
        """Dynamically reload environment variables so newly added keys in .env are picked up immediately."""
        from dotenv import load_dotenv
        if Config.ENV_PATH.exists():
            load_dotenv(dotenv_path=Config.ENV_PATH, override=True)
        if Config.BACKEND_ENV_PATH.exists():
            load_dotenv(dotenv_path=Config.BACKEND_ENV_PATH, override=True)

    @property
    def pollinations_key(self) -> str:
        self._refresh_env()
        return os.getenv("POLLINATIONS_API_KEY", "").strip() or Config.POLLINATIONS_API_KEY

    @property
    def replicate_token(self) -> str:
        self._refresh_env()
        return os.getenv("REPLICATE_API_TOKEN", "").strip() or Config.REPLICATE_API_TOKEN

    @property
    def hf_token(self) -> str:
        self._refresh_env()
        return os.getenv("HUGGINGFACE_API_KEY", "").strip() or os.getenv("HF_TOKEN", "").strip() or Config.HUGGINGFACE_API_KEY

    @property
    def modelslab_key(self) -> str:
        self._refresh_env()
        return os.getenv("MODELSLAB_API_KEY", "").strip() or Config.MODELSLAB_API_KEY

    @property
    def runware_key(self) -> str:
        self._refresh_env()
        return os.getenv("RUNWARE_API_KEY", "").strip()

    def get_available_providers(self) -> Dict[str, Any]:
        """Check which video generation backends are configured."""
        pol = bool(self.pollinations_key)
        rep = bool(self.replicate_token)
        hf = bool(self.hf_token)
        rw = bool(self.runware_key)
        ml = bool(self.modelslab_key)

        return {
            "pollinations": pol,
            "replicate": rep,
            "huggingface": hf,
            "runware": rw,
            "modelslab": ml,
            "any_available": bool(pol or rep or hf or rw or ml),
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

        # 1. Hugging Face ZeroGPU (Priority 1 - Free ZeroGPU Inference)
        if providers["huggingface"]:
            self._update_job(job_id, progress=25, message="Synthesizing video with Hugging Face ZeroGPU (LTX-Video)...")
            success, res = self._generate_hf_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("error"):
                provider_notes.append(res.get("error"))
                self._update_job(job_id, progress=45, message="Hugging Face busy. Switching to secondary video providers...")

        # 2. Pollinations Video (Priority 2)
        if providers["pollinations"]:
            self._update_job(job_id, progress=50, message="Synthesizing with Pollinations AI...")
            success, res = self._generate_pollinations_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("insufficient_balance"):
                provider_notes.append("Pollinations: Account has 0.00 pollen balance (~0.60 pollen required per video). Top up at https://enter.pollinations.ai")
                self._update_job(job_id, progress=65, message="Pollinations balance is 0.00. Switching automatically to Replicate AI...")
            elif res.get("error"):
                provider_notes.append(f"Pollinations: {res.get('error')}")

        # 3. Replicate Video API (Priority 3)
        if providers["replicate"]:
            self._update_job(job_id, progress=70, message="Synthesizing video with Replicate AI...")
            success, res = self._generate_replicate_video(prompt, mode, image_data)
            if success:
                self._finalize_job_success(job_id, user_id, res["video_bytes"], prompt, aspect_ratio, res["provider"], res["model"])
                return
            elif res.get("error"):
                provider_notes.append(res.get("error"))
                self._update_job(job_id, progress=85, message="Replicate unavailable. Checking ModelsLab...")

        # 4. ModelsLab (Priority 4)
        if providers["modelslab"]:
            self._update_job(job_id, progress=90, message="Dispatching to ModelsLab Video API...")
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
        error_details = "\n\n".join(provider_notes) if provider_notes else (
            "No active AI Video Provider API key configured.\n"
            "High-performance video generation (Text-to-Video & Image-to-Video) requires GPU credits.\n"
            "To enable video generation, please configure one of the following in your .env file:\n"
            "- POLLINATIONS_API_KEY (with pollen credit from enter.pollinations.ai)\n"
            "- REPLICATE_API_TOKEN (with credit from replicate.com/account/billing)\n"
            "- HUGGINGFACE_API_KEY / HF_TOKEN (from huggingface.co/settings/tokens)"
        )

        self._update_job(
            job_id,
            status="failed",
            progress=100,
            error=error_details,
            message="Video synthesis halted: All configured video providers were unavailable or out of credit.",
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
            return False, {"error": f"Pollinations returned HTTP {res.status_code}"}
        except Exception as e:
            logger.error("Pollinations video error: %s", e)
            return False, {"error": f"Pollinations connection error: {str(e)}"}

    def _generate_replicate_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call Replicate video generation model (AnimateDiff for T2V, SVD for I2V)."""
        headers = {
            "Authorization": f"Bearer {self.replicate_token}",
            "Content-Type": "application/json",
        }
        
        url = "https://api.replicate.com/v1/predictions"
        if mode == "image-to-video" or (image_data and mode != "text-to-video"):
            version = "3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438"
            payload_input = {
                "input_image": image_data if image_data else "https://replicate.delivery/pbxt/JR3pZ2e60xZ56s8u6a7/demo.jpg",
                "sizing_strategy": "maintain_aspect_ratio",
                "frames_per_second": 6,
                "motion_bucket_id": 127,
            }
            model_label = "Stable Video Diffusion (SVD)"
        else:
            version = "beecf59c4aee8d81bf04f0381033dfa10dc16e845b4ae00d281e2fa377e48a9f"
            payload_input = {
                "prompt": prompt,
                "n_prompt": "bad quality, blurry, low resolution, glitch, artifacts",
                "steps": 25,
            }
            model_label = "AnimateDiff (T2V)"

        payload = {"version": version, "input": payload_input}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if not res.ok:
                err_detail = "API error"
                try:
                    err_json = res.json()
                    err_detail = err_json.get("detail") or err_json.get("title") or res.text[:120]
                except Exception:
                    err_detail = f"HTTP {res.status_code}"
                return False, {"error": f"Replicate: {err_detail}"}
            
            pred = res.json()
            poll_url = pred.get("urls", {}).get("get")
            if not poll_url:
                return False, {"error": "Replicate: Missing poll URL"}

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
                                "model": model_label,
                            }
                elif status in ("failed", "canceled"):
                    return False, {"error": f"Replicate: {chk.get('error', 'Prediction failed')}"}
        except Exception as e:
            logger.error("Replicate video request error: %s", e)
            return False, {"error": f"Replicate error: {str(e)}"}

        return False, {"error": "Replicate: Video generation timed out"}

    def _generate_hf_video(self, prompt: str, mode: str, image_data: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
        """Call free Hugging Face ZeroGPU space using gradio_client."""
        try:
            from gradio_client import Client, handle_file
        except ImportError:
            return False, {"error": "Hugging Face: gradio_client is not installed"}

        token = self.hf_token
        spaces = [
            ("Lightricks/ltx-video-distilled", "Lightricks LTX-Video [Free ZeroGPU]"),
            ("DeepRat/LTX-Video-ZeroGPU-Optimized", "LTX-Video ZeroGPU Optimized"),
        ]

        temp_img_file = None
        if (mode == "image-to-video" or image_data) and image_data:
            try:
                if "," in image_data:
                    b64_str = image_data.split(",", 1)[1]
                else:
                    b64_str = image_data
                img_bytes = base64.b64decode(b64_str)
                temp_img_file = Config.UPLOAD_DIR / f"temp_i2v_{uuid.uuid4().hex[:8]}.jpg"
                with open(temp_img_file, "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                logger.warning("Could not decode image_data for I2V: %s", e)

        for space_name, model_label in spaces:
            try:
                logger.info("Attempting Hugging Face ZeroGPU Space: %s...", space_name)
                client = Client(space_name, token=token)

                if temp_img_file and temp_img_file.exists():
                    # Call Image-to-Video endpoint
                    res = client.predict(
                        prompt=prompt,
                        negative_prompt="blurry, low quality, jittery, distorted",
                        input_image_filepath=handle_file(str(temp_img_file)),
                        input_video_filepath=None,
                        height_ui=512,
                        width_ui=704,
                        mode="image-to-video",
                        duration_ui=2,
                        ui_frames_to_use=9,
                        seed_ui=42,
                        randomize_seed=True,
                        ui_guidance_scale=1,
                        improve_texture_flag=True,
                        api_name="/image_to_video"
                    )
                else:
                    # Call Text-to-Video endpoint
                    res = client.predict(
                        prompt=prompt,
                        negative_prompt="blurry, low quality, jittery, distorted",
                        input_image_filepath=None,
                        input_video_filepath=None,
                        height_ui=512,
                        width_ui=704,
                        mode="text-to-video",
                        duration_ui=2,
                        ui_frames_to_use=9,
                        seed_ui=42,
                        randomize_seed=True,
                        ui_guidance_scale=1,
                        improve_texture_flag=True,
                        api_name="/text_to_video"
                    )

                # Process returned video output
                video_filepath = None
                if isinstance(res, (tuple, list)) and len(res) > 0:
                    video_info = res[0]
                    if isinstance(video_info, dict):
                        video_filepath = video_info.get("video")
                    elif isinstance(video_info, str):
                        video_filepath = video_info

                if video_filepath and os.path.exists(video_filepath):
                    with open(video_filepath, "rb") as vf:
                        v_bytes = vf.read()
                    if len(v_bytes) > 5000:
                        if temp_img_file and temp_img_file.exists():
                            try: temp_img_file.unlink()
                            except Exception: pass
                        return True, {
                            "video_bytes": v_bytes,
                            "provider": f"Hugging Face ({space_name})",
                            "model": model_label,
                        }

            except Exception as e:
                logger.warning("Space %s error: %s", space_name, e)
                continue

        if temp_img_file and temp_img_file.exists():
            try: temp_img_file.unlink()
            except Exception: pass

        return False, {"error": "Hugging Face: ZeroGPU video spaces were busy. Please retry in a few moments."}

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
                if data.get("status") == "error":
                    return False, {"error": f"ModelsLab: {data.get('message', 'Subscription required')}"}
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
            return False, {"error": f"ModelsLab connection error: {str(e)}"}

        return False, {"error": "ModelsLab: Failed to synthesize video."}

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
