"""
Unit tests for Videeo.ai Stage 1 Pipeline.
"""

import pytest
from datetime import datetime

# Test models
from models.schemas import (
    GenerateRequest,
    GenerateResponse,
    StatusResponse,
    DownloadResponse,
    JobStatus,
    Scene,
    VideoScript,
    JobState,
    AspectRatio
)

# Test job manager
from services.job_manager import JobManager


class TestModels:
    """Test Pydantic models."""
    
    def test_generate_request_valid(self):
        """Test valid generate request."""
        request = GenerateRequest(
            prompt="A coffee shop owner discovers AI",
            scenes=5,
            aspect_ratio=AspectRatio.LANDSCAPE
        )
        assert request.prompt == "A coffee shop owner discovers AI"
        assert request.scenes == 5
        assert request.aspect_ratio == AspectRatio.LANDSCAPE
    
    def test_generate_request_defaults(self):
        """Test generate request with defaults."""
        request = GenerateRequest(prompt="Test prompt for video generation")
        assert request.scenes == 5
        assert request.aspect_ratio == AspectRatio.LANDSCAPE
    
    def test_generate_request_invalid_prompt(self):
        """Test generate request with too short prompt."""
        with pytest.raises(ValueError):
            GenerateRequest(prompt="Short")
    
    def test_scene_model(self):
        """Test Scene model."""
        scene = Scene(
            scene_number=1,
            visual_description="A woman sits at a desk looking at laptop",
            dialogue="The future of business is here..."
        )
        assert scene.scene_number == 1
        assert scene.image_url is None
        assert scene.video_url is None
    
    def test_video_script_model(self):
        """Test VideoScript model."""
        scenes = [
            Scene(scene_number=1, visual_description="Opening shot", dialogue="Hello"),
            Scene(scene_number=2, visual_description="Second shot", dialogue="World")
        ]
        script = VideoScript(
            character_description="Young professional woman",
            scenes=scenes
        )
        assert len(script.scenes) == 2
        assert script.character_description == "Young professional woman"
    
    def test_job_status_enum(self):
        """Test JobStatus enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.COMPLETE.value == "complete"
        assert JobStatus.ERROR.value == "error"


class TestJobManager:
    """Test JobManager service."""
    
    def setup_method(self):
        """Set up fresh JobManager for each test."""
        self.manager = JobManager()
    
    def test_create_job(self):
        """Test job creation."""
        job = self.manager.create_job(
            prompt="Test prompt",
            scene_count=5
        )
        
        assert job.job_id.startswith("vid_")
        assert job.status == JobStatus.PENDING
        assert job.prompt == "Test prompt"
        assert job.scene_count == 5
        assert job.progress_percent == 0
    
    def test_get_job(self):
        """Test retrieving a job."""
        created = self.manager.create_job("Test prompt")
        retrieved = self.manager.get_job(created.job_id)
        
        assert retrieved is not None
        assert retrieved.job_id == created.job_id
    
    def test_get_nonexistent_job(self):
        """Test retrieving non-existent job."""
        job = self.manager.get_job("vid_doesnotexist")
        assert job is None
    
    def test_update_job(self):
        """Test updating job status."""
        job = self.manager.create_job("Test prompt")
        
        updated = self.manager.update_job(
            job.job_id,
            status=JobStatus.GENERATING_SCRIPT,
            progress_percent=10,
            current_step="Generating script..."
        )
        
        assert updated.status == JobStatus.GENERATING_SCRIPT
        assert updated.progress_percent == 10
        assert updated.current_step == "Generating script..."
    
    def test_set_error(self):
        """Test setting job to error state."""
        job = self.manager.create_job("Test prompt")
        
        self.manager.set_error(job.job_id, "Something went wrong")
        
        updated = self.manager.get_job(job.job_id)
        assert updated.status == JobStatus.ERROR
        assert updated.error_message == "Something went wrong"
    
    def test_set_complete(self):
        """Test setting job to complete state."""
        job = self.manager.create_job("Test prompt")
        
        self.manager.set_complete(
            job.job_id,
            video_url="https://example.com/video.mp4",
            duration_seconds=30
        )
        
        updated = self.manager.get_job(job.job_id)
        assert updated.status == JobStatus.COMPLETE
        assert updated.progress_percent == 100
        assert updated.video_url == "https://example.com/video.mp4"
        assert updated.duration_seconds == 30
    
    def test_delete_job(self):
        """Test deleting a job."""
        job = self.manager.create_job("Test prompt")
        
        assert self.manager.delete_job(job.job_id) is True
        assert self.manager.get_job(job.job_id) is None
    
    def test_delete_nonexistent_job(self):
        """Test deleting non-existent job."""
        assert self.manager.delete_job("vid_doesnotexist") is False


class TestAPIEndpoints:
    """Test FastAPI endpoints using TestClient."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)
    
    def test_root_endpoint(self, client):
        """Test health check root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_health_endpoint(self, client):
        """Test detailed health check."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert "config" in data
    
    def test_generate_endpoint(self, client):
        """Test video generation endpoint."""
        response = client.post("/generate", json={
            "prompt": "A coffee shop owner discovers AI and transforms her business in 30 days",
            "scenes": 5,
            "aspect_ratio": "16:9"
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "estimated_time_seconds" in data
    
    def test_generate_invalid_prompt(self, client):
        """Test generate with invalid prompt."""
        response = client.post("/generate", json={
            "prompt": "Short"
        })
        assert response.status_code == 422  # Validation error
    
    def test_status_not_found(self, client):
        """Test status for non-existent job."""
        response = client.get("/status/vid_doesnotexist")
        assert response.status_code == 404
    
    def test_download_not_found(self, client):
        """Test download for non-existent job."""
        response = client.get("/download/vid_doesnotexist")
        assert response.status_code == 404


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
