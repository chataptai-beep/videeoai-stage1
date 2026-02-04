"""
Videeo.ai Stage 1 Pipeline - FastAPI Main Application

A production-ready backend that transforms text prompts into polished,
multi-scene AI videos with native video generation and frame continuity.

Author: AsaanAI
Version: 1.0.0
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models.schemas import (
    GenerateRequest,
    GenerateResponse,
    StatusResponse,
    DownloadResponse,
    JobStatus,
    AspectRatio
)
from services.job_manager import job_manager
from pipeline.orchestrator import PipelineOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# === Lifespan Events ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events for startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    
    # Create required directories
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    
    # Validate API keys
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set - script generation will fail")
    if not settings.kie_api_key:
        logger.warning("KIE_API_KEY not set - image/video generation will fail")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Videeo.ai Pipeline...")


# === FastAPI App ===

app = FastAPI(
    title=settings.app_name,
    description="""
    ## Videeo.ai Stage 1 Pipeline API
    
    Transform text prompts into polished, multi-scene AI videos.
    
    ### Features
    - **Script Generation**: GPT-4o-mini powered scene scripting
    - **AI Video Generation**: Native Veo 3 video clips (not slideshows)
    - **Frame Continuity**: Seamless transitions between scenes
    - **Caption Burn-in**: Professional text overlays
    
    ### Workflow
    1. `POST /generate` - Submit a video generation job
    2. `GET /status/{job_id}` - Poll for job status and progress
    3. `GET /download/{job_id}` - Get the final video URL
    """,
    version=settings.app_version,
    lifespan=lifespan
)

# === Rate Limiting (Bonus Point) ===
# Max 5 requests per IP per hour
ip_request_history = {} # {ip: [timestamp1, timestamp2, ...]}

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
        client_ip = request.client.host
        now = datetime.utcnow().timestamp()
        
        # Filter history for last hour
        one_hour_ago = now - 3600
        history = [ts for ts in ip_request_history.get(client_ip, []) if ts > one_hour_ago]
        
        if len(history) >= 5:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Max 5 requests per hour."}
            )
        
        # Update history
        history.append(now)
        ip_request_history[client_ip] = history
        
    return await call_next(request)


# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and outputs
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


# === API Endpoints ===

@app.get("/", tags=["Frontend"], response_class=HTMLResponse)
async def root():
    """Serve the frontend application."""
    index_path = Path("static/index.html")
    if not index_path.exists():
        return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check with configuration status."""
    return {
        "status": "healthy",
        "checks": {
            "openai_api_key": bool(settings.openai_api_key),
            "kie_api_key": bool(settings.kie_api_key),
            "cloudinary_configured": bool(settings.cloudinary_cloud_name),
        },
        "config": {
            "default_scene_count": settings.default_scene_count,
            "scene_duration_seconds": settings.scene_duration_seconds,
            "max_retries": settings.max_retries
        }
    }


@app.post(
    "/generate",
    response_model=GenerateResponse,
    tags=["Video Generation"],
    summary="Start video generation",
    description="Submit a text prompt to generate a multi-scene video."
)
async def generate_video(
    request: GenerateRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new video generation job.
    
    The job runs asynchronously in the background. Use the returned job_id
    to poll for status and eventually download the completed video.
    
    **Request Body:**
    - `prompt`: Text describing the video content (10-2000 chars)
    - `scenes`: Number of scenes (default: 5, max: 10)
    - `aspect_ratio`: Video aspect ratio (default: 16:9)
    
    **Response:**
    - `job_id`: Unique identifier for tracking the job
    - `status`: Current status (pending)
    - `estimated_time_seconds`: Estimated completion time
    """
    logger.info(f"New video generation request: {request.prompt[:50]}...")
    
    # Create the job
    job = job_manager.create_job(
        prompt=request.prompt,
        scene_count=request.scenes,
        aspect_ratio=request.aspect_ratio
    )
    
    # Start the pipeline in the background
    orchestrator = PipelineOrchestrator()
    background_tasks.add_task(orchestrator.run_pipeline, job.job_id)
    
    # Calculate estimated time (rough estimate based on scene count)
    estimated_time = request.scenes * 30 + 60  # ~30s per scene + 60s overhead
    
    logger.info(f"Job created: {job.job_id}")
    
    return GenerateResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        estimated_time_seconds=estimated_time
    )


@app.get(
    "/status/{job_id}",
    response_model=StatusResponse,
    tags=["Video Generation"],
    summary="Get job status",
    description="Get the current status and progress of a video generation job."
)
async def get_status(job_id: str):
    """
    Get the status of a video generation job.
    
    **Response:**
    - `job_id`: The job identifier
    - `status`: Current status (pending, generating_script, generating_images, etc.)
    - `progress_percent`: Progress as percentage (0-100)
    - `current_step`: Human-readable description of current step
    - `created_at`: Job creation timestamp
    - `error_message`: Error details if status is 'error'
    """
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}"
        )
    
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_step=job.current_step,
        created_at=job.created_at,
        error_message=job.error_message
    )


@app.get(
    "/download/{job_id}",
    response_model=DownloadResponse,
    tags=["Video Generation"],
    summary="Get download URL",
    description="Get the download URL for a completed video."
)
async def get_download(job_id: str):
    """
    Get the download URL for a completed video.
    
    **Response:**
    - `job_id`: The job identifier
    - `status`: Current status (should be 'complete' for successful download)
    - `video_url`: URL to download the video
    - `duration_seconds`: Video duration
    - `resolution`: Video resolution (e.g., "1920x1080")
    - `error_message`: Error details if job failed
    """
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}"
        )
    
    if job.status == JobStatus.ERROR:
        return DownloadResponse(
            job_id=job.job_id,
            status=job.status,
            error_message=job.error_message
        )
    
    if job.status != JobStatus.COMPLETE:
        return DownloadResponse(
            job_id=job.job_id,
            status=job.status,
            error_message=f"Video not ready. Current status: {job.status.value}"
        )
    
    return DownloadResponse(
        job_id=job.job_id,
        status=job.status,
        video_url=job.video_url,
        duration_seconds=job.duration_seconds,
        resolution=f"{settings.video_width}x{settings.video_height}"
    )


# === Debug Endpoints (development only) ===

@app.get("/jobs", tags=["Debug"], include_in_schema=settings.debug)
async def list_jobs():
    """List all jobs (debug endpoint)."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    
    jobs = job_manager.get_all_jobs()
    return {
        "total": len(jobs),
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "progress": j.progress_percent,
                "created_at": j.created_at.isoformat()
            }
            for j in jobs.values()
        ]
    }


@app.delete("/jobs/{job_id}", tags=["Debug"], include_in_schema=settings.debug)
async def delete_job(job_id: str):
    """Delete a job (debug endpoint)."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    
    if job_manager.delete_job(job_id):
        return {"deleted": job_id}
    else:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


# === File Download (for local files) ===

@app.get("/files/{filename}", tags=["Files"])
async def download_local_file(filename: str):
    """Download a locally stored video file."""
    file_path = Path(settings.output_dir) / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="video/mp4"
    )


# === Run Server ===

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
