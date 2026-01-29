"""
Video Generator using kie.ai API with Veo 3 model.
Generates video clips for each scene with frame continuity.
"""

import asyncio
import json
import logging
from typing import Optional

import httpx

from config import settings
from models.schemas import Scene, AspectRatio

logger = logging.getLogger(__name__)


class VideoGenerator:
    """
    Generates video clips using kie.ai's Veo 3 model.
    Supports frame continuity by using reference images.
    """
    
    def __init__(self):
        self.api_key = settings.kie_api_key
        self.base_url = "https://api.kie.ai/api/v1"  # Correct kie.ai API base
        self.poll_interval = settings.api_poll_interval_seconds
    
    async def generate_scene_video(
        self,
        scene: Scene,
        reference_image_url: str,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        scene_index: int = 0,
        character_description: str = "",
        background_theme: str = ""
    ) -> str:
        """
        Generate a video clip for a single scene.
        
        Args:
            scene: Scene object with visual description and dialogue
            reference_image_url: URL to reference image (character or last frame)
            aspect_ratio: Video aspect ratio
            scene_index: Index of the scene (0-based, used for continuity logic)
            character_description: Description of the main character
            background_theme: Background setting for the video
        
        Returns:
            URL to the generated video
        
        Raises:
            Exception: If generation fails
        """
        # Build the video generation prompt
        prompt = self._build_video_prompt(
            scene=scene,
            scene_index=scene_index,
            character_description=character_description,
            background_theme=background_theme
        )
        
        logger.info(f"Generating video for Scene {scene.scene_number}...")
        
        # Step 1: Create the video generation task
        task_id = await self._create_video_task(
            prompt=prompt,
            reference_image_url=reference_image_url,
            aspect_ratio=aspect_ratio
        )
        
        # Step 2: Poll for completion (video gen takes longer)
        video_url = await self._poll_for_result(task_id, max_attempts=120)
        
        logger.info(f"Video generated for Scene {scene.scene_number}: {video_url}")
        return video_url
    
    def _build_video_prompt(
        self,
        scene: Scene,
        scene_index: int,
        character_description: str,
        background_theme: str
    ) -> str:
        """Build an optimized prompt for video generation."""
        
        prompt_parts = []
        
        # Scene continuity instructions
        if scene_index == 0:
            # First scene: use reference image for character only
            prompt_parts.append(
                "Provide a cinematic video shot starting IMMEDIATELY in media res. "
                "Use the reference image for character likeness and outfit ONLY. "
                "Critically, IGNORE the neutral pose in the reference image."
            )
        else:
            # Subsequent scenes: continue from previous scene's last frame
            prompt_parts.append(
                "Continue seamlessly from the reference image. "
                "CRITICAL: The reference image shows the EXACT ending frame of the previous scene. "
                "START in this exact pose/position. Maintain perfect continuity."
            )
        
        # Visual description
        prompt_parts.append(
            f"AT START (t=0s): {scene.visual_description}"
        )
        
        # Background
        if background_theme:
            prompt_parts.append(f"BACKGROUND: {background_theme}")
        
        # Style instructions
        prompt_parts.append(
            "STYLE: The shot must be hyper-realistic, 4K, cinematic, "
            "with natural lighting and detailed textures. "
            "Keep camera movement steady and fluid. "
            "Maintain consistent lighting throughout the shot."
        )
        
        # Audio instructions
        prompt_parts.append(
            "AUDIO: Cinematic sound effects matching the action, "
            "realistic ambient noise, high fidelity."
        )
        
        # Critical: No text overlays (we add captions ourselves)
        prompt_parts.append(
            "CRITICAL: Do not display any text, subtitles, watermarks, "
            "or UI elements. Clean cinematic footage only."
        )
        
        return " ".join(prompt_parts)
    
    async def _create_video_task(
        self,
        prompt: str,
        reference_image_url: str,
        aspect_ratio: AspectRatio
    ) -> str:
        """Create a video generation task and return the task ID."""
        
        # Map aspect ratio to kie.ai format
        ar_map = {
            AspectRatio.LANDSCAPE: "16:9",
            AspectRatio.PORTRAIT: "9:16",
            AspectRatio.SQUARE: "1:1"
        }
        
        try:
            # Use longer timeouts to avoid 522 errors
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=60.0, pool=60.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                # Based on n8n workflow, kie.ai Veo 3 uses form data format
                response = await client.post(
                    f"{self.base_url}/veo/generate",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "Videeo-Pipeline/1.0"
                    },
                    json={
                        "model": "veo3_fast",  # Fast mode: 60 credits vs Quality: 250 credits
                        "prompt": prompt,
                        "aspectRatio": ar_map.get(aspect_ratio, "16:9"),
                        "imageUrls": reference_image_url,
                        "generationType": "FIRST_AND_LAST_FRAMES_2_VIDEO",
                        "seeds": "12345",
                        "negative_prompt": "text, subtitles, watermark, logo, signature, typography, blurred, distorted"
                    }
                )
                
                response.raise_for_status()
                
                # Log raw response for debugging
                raw_text = response.text
                logger.info(f"veo/generate raw response: {raw_text[:500]}")
                
                data = response.json()
                
                # Safely access nested data
                if isinstance(data, dict):
                    inner_data = data.get("data", {})
                    if isinstance(inner_data, dict):
                        task_id = inner_data.get("taskId")
                    else:
                        logger.warning(f"Unexpected inner data type: {type(inner_data)}")
                        task_id = None
                    
                    if not task_id:
                        task_id = data.get("taskId") or data.get("task_id") or data.get("id")
                else:
                    logger.error(f"Unexpected response type: {type(data)}, value: {data}")
                    raise Exception(f"Unexpected response format: {data}")
                
                if not task_id:
                    raise Exception(f"No task ID in response: {data}")
                
                logger.info(f"Video task created: {task_id}")
                return task_id
                
        except httpx.HTTPStatusError as e:
            logger.error(f"kie.ai Veo API error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Video generation failed: {e.response.status_code} - {e.response.text}")
    
    async def _poll_for_result(
        self,
        task_id: str,
        max_attempts: int = 120  # 20 minutes with 10s poll interval
    ) -> str:
        """Poll for task completion and return the video URL."""
        
        for attempt in range(max_attempts):
            try:
                # Use longer timeouts to avoid 522 errors
                timeout = httpx.Timeout(connect=30.0, read=90.0, write=30.0, pool=30.0)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    # kie.ai Veo uses record-info endpoint with query param
                    response = await client.get(
                        f"{self.base_url}/veo/record-info",
                        params={"taskId": task_id},
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "User-Agent": "Videeo-Pipeline/1.0"
                        }
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Log full response on first attempt and periodically
                    if attempt == 0 or attempt % 6 == 0:
                        logger.info(f"veo/record-info response (attempt {attempt + 1}): {json.dumps(data)[:500]}")
                    
                    # Safely extract state - kie.ai uses successFlag (1=success, 0=pending)
                    # NOT "state" as string!
                    is_success = False
                    is_failed = False
                    inner_data = {}
                    
                    if isinstance(data, dict):
                        # CRITICAL: Check top-level API error first
                        api_code = data.get("code")
                        api_msg = data.get("msg", "")
                        
                        # Handle API-level errors (code != 200)
                        if api_code is not None and api_code != 200:
                            error_message = f"{api_code} - {api_msg}"
                            logger.error(f"Video generation failed: {error_message}")
                            raise Exception(f"Video generation failed: {error_message}")
                        
                        inner_data = data.get("data", {})
                        if isinstance(inner_data, dict):
                            # Check successFlag (1 = completed successfully)
                            success_flag = inner_data.get("successFlag")
                            if success_flag == 1:
                                is_success = True
                            
                            # Check for task-level errors
                            error_code = inner_data.get("errorCode")
                            error_msg = inner_data.get("errorMessage")
                            if error_code is not None or (error_msg is not None and error_msg != ""):
                                is_failed = True
                                logger.error(f"Video generation failed: {error_code} - {error_msg}")
                    
                    if is_success:
                        # KEY FINDING: Veo returns data.response.resultUrls[0]
                        video_url = None
                        
                        if isinstance(data, dict):
                            inner_data = data.get("data", {})
                            if isinstance(inner_data, dict):
                                response_data = inner_data.get("response", {})
                                if isinstance(response_data, dict):
                                    result_urls = response_data.get("resultUrls", [])
                                    if result_urls and len(result_urls) > 0:
                                        video_url = result_urls[0]
                        
                        # Fallback: try other common response formats
                        if not video_url:
                            output = None
                            if isinstance(data, dict):
                                inner_data = data.get("data", {})
                                if isinstance(inner_data, dict):
                                    output = inner_data.get("output")
                                if not output:
                                    output = data.get("output")
                            
                            if isinstance(output, str) and output.startswith("http"):
                                video_url = output
                            elif isinstance(output, dict):
                                video_url = output.get("video_url") or output.get("url") or output.get("video")
                            elif isinstance(output, list) and len(output) > 0:
                                first = output[0]
                                if isinstance(first, str) and first.startswith("http"):
                                    video_url = first
                                elif isinstance(first, dict):
                                    video_url = first.get("url") or first.get("video_url")
                        
                        # Also check for direct URL fields
                        if not video_url and isinstance(data, dict):
                            inner_data = data.get("data", {})
                            if isinstance(inner_data, dict):
                                video_url = (
                                    inner_data.get("videoUrl") or
                                    inner_data.get("video_url") or
                                    inner_data.get("url")
                                )
                            if not video_url:
                                video_url = data.get("videoUrl") or data.get("video_url")
                        
                        if video_url:
                            return video_url
                        else:
                            raise Exception(f"No video URL in completed response: {data}")
                    
                    elif is_failed:
                        error = inner_data.get("errorMessage") or inner_data.get("errorCode") or "Unknown error"
                        raise Exception(f"Video generation failed: {error}")
                    
                    else:
                        # Still processing (successFlag = 0), wait and retry
                        if attempt % 6 == 0:  # Log every minute
                            success_flag = inner_data.get("successFlag", "unknown") if isinstance(inner_data, dict) else "unknown"
                            logger.info(f"Video task {task_id} successFlag: {success_flag}, waiting... ({attempt * self.poll_interval}s elapsed)")
                        await asyncio.sleep(self.poll_interval)
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.debug(f"Task {task_id} not found yet, retrying...")
                    await asyncio.sleep(self.poll_interval)
                else:
                    logger.error(f"HTTP error polling task: {e}")
                    # Don't crash on random 500/502s, just retry a few times?
                    # valid 500s from API might mean transient failure.
                    # Let's count consecutive errors or just wait and retry.
                    await asyncio.sleep(self.poll_interval)
            
            except httpx.RequestError as e:
                # Catch timeouts (ReadTimeout, ConnectTimeout) and connection errors
                logger.warning(f"Network error polling task {task_id}: {e}. Retrying...")
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Unexpected error polling task {task_id}: {e}")
                # For safety, maybe verify if it is a fatal code error or transient
                await asyncio.sleep(self.poll_interval)
        
        raise Exception(f"Video generation timed out after {max_attempts * self.poll_interval} seconds")
