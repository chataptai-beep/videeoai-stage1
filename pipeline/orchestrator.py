"""
Pipeline Orchestrator - Coordinates the entire video generation pipeline.
Manages the flow from prompt to final video with status updates.
"""

import asyncio
import logging
from typing import Optional

import httpx
from pathlib import Path

from config import settings
from models.schemas import JobState, JobStatus, Scene, VideoScript, AspectRatio
from services.job_manager import job_manager
from .script_generator import ScriptGenerator
from .image_generator import ImageGenerator
from .video_generator import VideoGenerator
from .video_stitcher import VideoStitcher
from .caption_burner import CaptionBurner

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Orchestrates the complete video generation pipeline.
    
    Pipeline stages:
    1. Script Generation (LLM)
    2. Reference Image Generation (kie.ai Nano Banana)
    3. Scene Video Generation (kie.ai Veo 3)
    4. Video Stitching (FFmpeg)
    5. Caption Burn-in (FFmpeg)
    6. Upload to CDN (Cloudinary)
    """
    
    def __init__(self):
        self.script_generator = ScriptGenerator()
        self.image_generator = ImageGenerator()
        self.video_generator = VideoGenerator()
        self.video_stitcher = VideoStitcher()
        self.caption_burner = CaptionBurner()
        
        # Cloudinary config
        self.cloudinary_cloud = settings.cloudinary_cloud_name
        self.cloudinary_key = settings.cloudinary_api_key
        self.cloudinary_secret = settings.cloudinary_api_secret
    
    async def run_pipeline(self, job_id: str) -> None:
        """
        Run the complete video generation pipeline for a job.
        
        This method runs in the background and updates job status as it progresses.
        """
        job = job_manager.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        try:
            # Stage 1: Script Generation (0-15%)
            await self._stage_script_generation(job)
            
            # Stage 2: Reference Image Generation (15-25%)
            await self._stage_image_generation(job)
            
            # Stage 3: Scene Video Generation (25-70%)
            await self._stage_video_generation(job)
            
            # Stage 4: Video Stitching (70-85%)
            await self._stage_video_stitching(job)
            
            # Stage 5: Caption Burn-in (85-95%)
            await self._stage_caption_burnin(job)
            
            # Stage 6: Upload and Finalize (95-100%)
            await self._stage_upload_and_finalize(job)
            
        except Exception as e:
            logger.exception(f"Pipeline failed for job {job_id}: {e}")
            self._handle_error(job_id, str(e))
    
    async def _stage_script_generation(self, job: JobState) -> None:
        """Stage 1: Generate the video script using LLM."""
        job_manager.update_job(
            job.job_id,
            status=JobStatus.GENERATING_SCRIPT,
            progress_percent=5,
            current_step="Generating video script..."
        )
        
        try:
            script = await self._with_retry(
                lambda: self.script_generator.generate(job.prompt, job.scene_count),
                "Script generation"
            )
            
            job_manager.update_job(
                job.job_id,
                script=script,
                progress_percent=15,
                current_step=f"Script generated: {len(script.scenes)} scenes"
            )
            
            logger.info(f"Job {job.job_id}: Script generated with {len(script.scenes)} scenes")
            
        except Exception as e:
            raise Exception(f"Script generation failed: {e}")
    
    async def _stage_image_generation(self, job: JobState) -> None:
        """Stage 2: Generate reference character image."""
        job_manager.update_job(
            job.job_id,
            status=JobStatus.GENERATING_IMAGES,
            progress_percent=17,
            current_step="Generating reference character image..."
        )
        
        # Get updated job with script
        job = job_manager.get_job(job.job_id)
        
        try:
            # Generate optimized image prompt
            image_prompts = await self.script_generator.generate_image_prompt(
                job.script.character_description
            )
            
            # Generate the reference image
            reference_image_url = await self._with_retry(
                lambda: self.image_generator.generate(
                    prompt=image_prompts["image_prompt"],
                    negative_prompt=image_prompts.get("negative_prompt", "")
                ),
                "Image generation"
            )
            
            job_manager.update_job(
                job.job_id,
                reference_image_url=reference_image_url,
                progress_percent=25,
                current_step="Reference image generated"
            )
            
            logger.info(f"Job {job.job_id}: Reference image generated: {reference_image_url}")
            
        except Exception as e:
            raise Exception(f"Image generation failed: {e}")
    
    async def _stage_video_generation(self, job: JobState) -> None:
        """Stage 3: Generate video for each scene using Veo 3."""
        job_manager.update_job(
            job.job_id,
            status=JobStatus.GENERATING_VIDEOS,
            progress_percent=27,
            current_step="Generating scene videos..."
        )
        
        # Get updated job
        job = job_manager.get_job(job.job_id)
        
        scene_videos = []
        total_scenes = len(job.script.scenes)
        
        # Progress range: 27% to 70% (43% total for all scenes)
        progress_per_scene = 43 / total_scenes
        
        # Reference image starts as the character reference
        current_reference = job.reference_image_url
        
        for i, scene in enumerate(job.script.scenes):
            job_manager.update_job(
                job.job_id,
                progress_percent=int(27 + (i * progress_per_scene)),
                current_step=f"Generating scene {i + 1} of {total_scenes}..."
            )
            
            try:
                video_url = await self._with_retry(
                    lambda: self.video_generator.generate_scene_video(
                        scene=scene,
                        reference_image_url=current_reference,
                        aspect_ratio=job.aspect_ratio,
                        scene_index=i,
                        character_description=job.script.character_description,
                        background_theme=job.script.background_theme or ""
                    ),
                    f"Scene {i + 1} video generation"
                )
                
                scene_videos.append(video_url)
                
                # Update scene with video URL
                scene.video_url = video_url
                
                # For frame continuity: extract last frame for next scene
                # (In full implementation, we'd upload to Cloudinary and extract frame)
                # For MVP, we'll continue using the same reference
                # TODO: Implement last-frame extraction for true continuity
                
                logger.info(f"Job {job.job_id}: Scene {i + 1} video generated")
                
            except Exception as e:
                logger.error(f"Failed to generate scene {i + 1}: {e}")
                raise Exception(f"Scene {i + 1} video generation failed: {e}")
        
        job_manager.update_job(
            job.job_id,
            scene_videos=scene_videos,
            progress_percent=70,
            current_step=f"All {total_scenes} scene videos generated"
        )
    
    async def _stage_video_stitching(self, job: JobState) -> None:
        """Stage 4: Stitch all scene videos together."""
        job_manager.update_job(
            job.job_id,
            status=JobStatus.ASSEMBLING_VIDEO,
            progress_percent=72,
            current_step="Stitching videos together..."
        )
        
        # Get updated job
        job = job_manager.get_job(job.job_id)
        
        try:
            output_filename = f"video_{job.job_id}"
            
            # Result is now (path, durations)
            stitch_result = await self._with_retry(
                lambda: self.video_stitcher.stitch_with_crossfade(
                    video_urls=job.scene_videos,
                    output_filename=output_filename
                ),
                "Video stitching"
            )
            stitched_path = stitch_result[0]
            scene_durations = stitch_result[1]
            
            # Store path temporarily (will be replaced with CDN URL)
            job_manager.update_job(
                job.job_id,
                video_url=stitched_path,
                scene_durations=scene_durations,
                progress_percent=85,
                current_step="Videos stitched successfully"
            )
            
            logger.info(f"Job {job.job_id}: Videos stitched to {stitched_path}")
            
        except Exception as e:
            raise Exception(f"Video stitching failed: {e}")
    
    async def _stage_caption_burnin(self, job: JobState) -> None:
        """Stage 5: Burn captions into the video."""
        job_manager.update_job(
            job.job_id,
            status=JobStatus.ADDING_CAPTIONS,
            progress_percent=87,
            current_step="Adding captions..."
        )
        
        # Get updated job
        job = job_manager.get_job(job.job_id)
        
        try:
            output_filename = f"final_{job.job_id}"
            
            captioned_path = await self._with_retry(
                lambda: self.caption_burner.burn_captions(
                    input_video_path=job.video_url,
                    scenes=job.script.scenes,
                    output_filename=output_filename,
                    scene_duration=settings.scene_duration_seconds,
                    scene_durations=job.scene_durations
                ),
                "Caption burning"
            )
            
            # Get video duration
            duration = await self.video_stitcher.get_video_duration(captioned_path)
            
            job_manager.update_job(
                job.job_id,
                video_url=captioned_path,
                duration_seconds=int(duration),
                progress_percent=95,
                current_step="Captions added successfully"
            )
            
            logger.info(f"Job {job.job_id}: Captions burned in, duration: {duration}s")
            
        except Exception as e:
            raise Exception(f"Caption burning failed: {e}")
    
    async def _stage_upload_and_finalize(self, job: JobState) -> None:
        """Stage 6: Upload to CDN and finalize job."""
        job_manager.update_job(
            job.job_id,
            progress_percent=97,
            current_step="Uploading to CDN..."
        )
        
        # Get updated job
        job = job_manager.get_job(job.job_id)
        
        try:
            # Upload to Cloudinary if configured and NOT a placeholder
            is_cloudinary_configured = (
                self.cloudinary_cloud and 
                self.cloudinary_cloud != "your-cloud-name" and
                self.cloudinary_key and 
                self.cloudinary_key != "your-cloudinary-key"
            )

            if is_cloudinary_configured:
                logger.info(f"Uploading to Cloudinary: {self.cloudinary_cloud}")
                cdn_url = await self._upload_to_cloudinary(job.video_url, job.job_id)
            else:
                # Use browser-friendly local path (e.g., /outputs/filename.mp4)
                video_filename = Path(job.video_url).name
                cdn_url = f"/outputs/{video_filename}"
                logger.warning(f"Cloudinary not configured, serving locally: {cdn_url}")
            
            # Mark job as complete
            job_manager.set_complete(
                job.job_id,
                video_url=cdn_url,
                duration_seconds=job.duration_seconds or 30
            )
            
            logger.info(f"Job {job.job_id}: Pipeline complete! Video URL: {cdn_url}")
            
        except Exception as e:
            raise Exception(f"Upload failed: {e}")
    
    async def _upload_to_cloudinary(self, video_path: str, job_id: str) -> str:
        """Upload video to Cloudinary and return the URL."""
        import base64
        import hashlib
        import time
        
        timestamp = int(time.time())
        public_id = f"videeo/{job_id}"
        
        # Generate signature
        params_to_sign = f"public_id={public_id}&timestamp={timestamp}{self.cloudinary_secret}"
        signature = hashlib.sha1(params_to_sign.encode()).hexdigest()
        
        # Upload using Cloudinary API
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(video_path, "rb") as f:
                files = {"file": f}
                data = {
                    "public_id": public_id,
                    "timestamp": timestamp,
                    "signature": signature,
                    "api_key": self.cloudinary_key
                }
                
                response = await client.post(
                    f"https://api.cloudinary.com/v1_1/{self.cloudinary_cloud}/video/upload",
                    files=files,
                    data=data
                )
                
                response.raise_for_status()
                result = response.json()
                
                return result.get("secure_url") or result.get("url")
    
    async def _with_retry(self, func, operation_name: str, max_retries: int = None):
        """Execute a function with retry logic."""
        max_retries = max_retries or settings.max_retries
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await func()
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"{operation_name} failed after {max_retries + 1} attempts: {e}")
        
        raise last_error
    
    def _handle_error(self, job_id: str, error_message: str):
        """Handle pipeline error by updating job state."""
        job_manager.set_error(job_id, error_message)
        logger.error(f"Job {job_id} failed: {error_message}")
