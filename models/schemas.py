"""
Pydantic schemas for API requests, responses, and internal data models.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# === Enums ===

class JobStatus(str, Enum):
    """Job status states as per client requirements."""
    PENDING = "pending"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_IMAGES = "generating_images"
    GENERATING_VIDEOS = "generating_videos"
    ASSEMBLING_VIDEO = "assembling_video"
    ADDING_CAPTIONS = "adding_captions"
    COMPLETE = "complete"
    ERROR = "error"


class AspectRatio(str, Enum):
    """Supported aspect ratios."""
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"


# === API Request/Response Models ===

class GenerateRequest(BaseModel):
    """Request body for POST /generate endpoint."""
    prompt: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Text prompt describing the video to generate"
    )
    scenes: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of scenes to generate (default: 5)"
    )
    aspect_ratio: AspectRatio = Field(
        default=AspectRatio.PORTRAIT,
        description="Aspect ratio (16:9, 9:16, 1:1)"
    )


class GenerateResponse(BaseModel):
    """Response body for POST /generate endpoint."""
    job_id: str
    status: JobStatus
    estimated_time_seconds: int = 180


class StatusResponse(BaseModel):
    """Response body for GET /status/{job_id} endpoint."""
    job_id: str
    status: JobStatus
    progress_percent: int = Field(ge=0, le=100)
    current_step: str
    created_at: datetime
    error_message: Optional[str] = None


class DownloadResponse(BaseModel):
    """Response body for GET /download/{job_id} endpoint."""
    job_id: str
    status: JobStatus
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    resolution: Optional[str] = None
    error_message: Optional[str] = None


# === Internal Data Models ===

class Scene(BaseModel):
    """Single scene in the video script."""
    scene_number: int = Field(ge=1, le=10)
    visual_description: str = Field(
        ...,
        description="What to show visually in this scene"
    )
    dialogue: str = Field(
        ...,
        max_length=100,
        description="Text overlay/dialogue for this scene (15-20 words max)"
    )
    # Generated during pipeline
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    last_frame_url: Optional[str] = None
    cloudinary_public_id: Optional[str] = None


class VideoScript(BaseModel):
    """Complete video script with all scenes."""
    character_description: str = Field(
        ...,
        description="Detailed description of the main character"
    )
    scenes: List[Scene]
    visual_style: Optional[str] = None
    background_theme: Optional[str] = None


class JobState(BaseModel):
    """Complete state for a video generation job."""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress_percent: int = 0
    current_step: str = "Initializing..."
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Input
    prompt: str
    scene_count: int = 5
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    
    # Generated data
    script: Optional[VideoScript] = None
    reference_image_url: Optional[str] = None
    scene_videos: List[str] = Field(default_factory=list)
    
    # Output
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
