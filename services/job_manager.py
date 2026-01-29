"""
Job Manager for tracking video generation jobs.
Uses in-memory dictionary for MVP (as per client requirements).
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from models.schemas import JobState, JobStatus, AspectRatio


class JobManager:
    """
    Manages video generation job states.
    Thread-safe for async FastAPI usage.
    """
    
    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
    
    def create_job(
        self,
        prompt: str,
        scene_count: int = 5,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    ) -> JobState:
        """Create a new video generation job."""
        job_id = f"vid_{uuid.uuid4().hex[:12]}"
        
        job = JobState(
            job_id=job_id,
            prompt=prompt,
            scene_count=scene_count,
            aspect_ratio=aspect_ratio,
            status=JobStatus.PENDING,
            progress_percent=0,
            current_step="Job created, waiting to start...",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self._jobs[job_id] = job
        return job
    
    def get_job(self, job_id: str) -> Optional[JobState]:
        """Get a job by ID."""
        return self._jobs.get(job_id)
    
    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress_percent: Optional[int] = None,
        current_step: Optional[str] = None,
        error_message: Optional[str] = None,
        **kwargs
    ) -> Optional[JobState]:
        """Update job state."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        
        if status is not None:
            job.status = status
        if progress_percent is not None:
            job.progress_percent = progress_percent
        if current_step is not None:
            job.current_step = current_step
        if error_message is not None:
            job.error_message = error_message
        
        # Update any additional fields passed as kwargs
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        job.updated_at = datetime.utcnow()
        return job
    
    def set_error(self, job_id: str, error_message: str) -> Optional[JobState]:
        """Set job to error state."""
        return self.update_job(
            job_id,
            status=JobStatus.ERROR,
            error_message=error_message,
            current_step=f"Error: {error_message[:50]}..."
        )
    
    def set_complete(
        self,
        job_id: str,
        video_url: str,
        duration_seconds: int
    ) -> Optional[JobState]:
        """Set job to complete state."""
        return self.update_job(
            job_id,
            status=JobStatus.COMPLETE,
            progress_percent=100,
            current_step="Video generation complete!",
            video_url=video_url,
            duration_seconds=duration_seconds
        )
    
    def get_all_jobs(self) -> Dict[str, JobState]:
        """Get all jobs (for debugging)."""
        return self._jobs.copy()
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job (for cleanup)."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False


# Singleton instance
job_manager = JobManager()
