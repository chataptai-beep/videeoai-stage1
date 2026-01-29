"""
Configuration module for Videeo.ai Stage 1 Pipeline.
Loads environment variables and provides typed configuration.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    openai_api_key: str = ""
    kie_api_key: str = ""
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    
    # Optional: Google Gemini as alternative to OpenAI
    google_api_key: Optional[str] = None
    
    # Application Settings
    app_name: str = "Videeo.ai Stage 1 Pipeline"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Pipeline Settings
    default_scene_count: int = 5
    scene_duration_seconds: int = 6
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30
    
    # Timeouts and Retries
    max_retries: int = 2
    pipeline_timeout_seconds: int = 300  # 5 minutes
    api_poll_interval_seconds: int = 10
    
    # Storage
    output_dir: str = "./outputs"
    temp_dir: str = "./temp"
    
    # kie.ai specific
    kie_base_url: str = "https://api.kie.ai/api/v1"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience function to get settings
settings = get_settings()
