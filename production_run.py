import asyncio
import logging
import sys
import os
from pipeline.orchestrator import PipelineOrchestrator
from models.schemas import JobState, VideoScript, AspectRatio, JobStatus
from services.job_manager import job_manager

# Setup logging to see progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("ProductionRun")

async def main():
    # 1. Configuration for the Rooftop AI Influencer video
    prompt = """Golden-hour sunlight on urban rooftop. AI influencer in 30s, tailored jacket, minimalist sneakers. City skyline background. 
    Dialogue: 'Everyone thinks AI is complicated, expensive, and locked behind some technical wall, but that’s only true if you don’t know how to approach it.'
    Scene move to laptop with live AI flows. Dialogue: 'I use AI every day to automate work, scale systems, and free up time. Most people get stuck because they try to learn everything at once.'
    Rooftop tracking shot. Dialogue: 'I built this system to solve problems for myself first, and then I realized anyone could do this if they had the right blueprint.'
    Close up golden light. Dialogue: 'If you want the exact guide I use, comment LIFEHACK and I’ll send you everything so you can start building immediately.'"""
    num_scenes = 5
    
    logger.info("🎬 Starting High-Energy Production Run...")
    logger.info(f"Target: Vertical 9:16, 2x Speed, Viral Pacing")
    
    # 2. Initialize Orchestrator
    orchestrator = PipelineOrchestrator()
    
    # 3. Create a Job manually
    # Note: JobManager.create_job generates its own ID and takes prompt as first arg
    job = job_manager.create_job(prompt=prompt, scene_count=num_scenes, aspect_ratio=AspectRatio.PORTRAIT)
    job_id = job.job_id
    logger.info(f"✅ Job Created! ID: {job_id}")
    job_manager.update_job(job_id, status=JobStatus.PENDING)
    
    try:
        # 4. Run the full pipeline
        # Note: run_pipeline updates the job object in job_manager
        await orchestrator.run_pipeline(job_id)
        
        final_job = job_manager.get_job(job_id)
        if final_job.status == JobStatus.COMPLETE:
            logger.info("🚀 PRODUCTION SUCCESS!")
            logger.info(f"Final Video: {final_job.video_url}")
        else:
            logger.error(f"❌ Production failed status: {final_job.status}")
            logger.error(f"Error: {final_job.error_message}")
            
    except Exception as e:
        logger.exception(f"💥 Fatal crash during production: {e}")

if __name__ == "__main__":
    asyncio.run(main())
