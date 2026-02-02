import asyncio
import logging
import os
from pathlib import Path
from pipeline.video_stitcher import VideoStitcher
from pipeline.caption_burner import CaptionBurner
from models.schemas import Scene, VideoScript

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProperRecovery")

async def main():
    # 1. Setup
    stitcher = VideoStitcher()
    burner = CaptionBurner()
    output_dir = Path("outputs")
    temp_dir = Path("temp")
    
    # 2. Define the scenes (from the latest generation)
    raw_scenes = [temp_dir / f"scene_{i}.mp4" for i in range(1, 7)]
    for s in raw_scenes:
        if not s.exists():
            logger.error(f"Missing raw scene: {s}")
            return

    # 3. Create Scene objects for dialogue (LinkedIn Strategy)
    dialogues = [
        "THE TRUTH ABOUT AI.",
        "Most people think AI is coming.",
        "They are WRONG.",
        "It is already here.",
        "And it's changing everything.",
        "Are you ready?"
    ]
    
    scenes_obj = []
    for i, d in enumerate(dialogues):
        scenes_obj.append(Scene(
            scene_number=i+1,
            visual_description="",
            dialogue=d,
            video_url=str(raw_scenes[i]) # Not used by stitcher after local path is set?
        ))

    # 4. Standardize (Vertical Crop 1080x1920, Native Speed, SS 1s for i>0)
    logger.info("Step 1: Standardizing scenes (Vertical Crop + Native Speed)...")
    # We must call _process_ffmpeg_sync manually or bypass it.
    # _process_ffmpeg_sync(local_videos, output_filename, crossfade_duration)
    # Actually, VideoStitcher.stitch_videos(job_id, scenes) is better but it downloads.
    # I'll call _process_ffmpeg_sync directly.
    
    # My fixed VideoStitcher._process_ffmpeg_sync (from Step 2577) takes:
    # (local_videos, output_filename, crossfade_duration)
    # Wait, No. The prototype changed. Let me check the file content again.
    
    # Actually, I'll just use the logic in a custom loop for complete control.
    
    std_videos = []
    durations = []
    target_w = 1080
    target_h = 1920
    crossfade_duration = 0.5
    
    for i, v in enumerate(raw_scenes):
        std_path = output_dir / f"recovered_std_scene_{i}.mp4"
        
        vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
              f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2,"
              f"setsar=1")
        
        input_args = ["-y"]
        if i > 0:
            input_args.extend(["-ss", "1.0"]) # Trim static ref frame
        input_args.extend(["-i", str(v)])
        
        cmd = [
            stitcher.ffmpeg_path, *input_args,
            "-vf", vf,
            "-r", "30",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(std_path)
        ]
        
        logger.info(f"Standardizing {v.name} -> {std_path.name}")
        import subprocess
        subprocess.run(cmd, check=True)
        std_videos.append(str(std_path))
        
        # Get duration
        cmd_dur = [stitcher.ffmpeg_path, "-i", str(std_path)]
        res_dur = subprocess.run(cmd_dur, capture_output=True, text=True)
        import re
        match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res_dur.stderr)
        if match:
             h, m, s = map(float, match.groups())
             durations.append(h*3600 + m*60 + s)
        else:
             durations.append(7.0)
             
    # 5. Stitch
    logger.info("Step 2: Stitching scenes together...")
    n = len(std_videos)
    inputs = []
    for v in std_videos:
        inputs.extend(["-i", v])
        
    filter_complex = ""
    prev_v = "[0:v]"
    prev_a = "[0:a]"
    cumulative_offset = 0.0
    
    for i in range(1, n):
        cumulative_offset += durations[i-1] - crossfade_duration
        out_v = f"v_fade_{i}"
        out_a = f"a_fade_{i}"
        filter_complex += f"{prev_v}[{i}:v]xfade=transition=fade:duration={crossfade_duration}:offset={cumulative_offset}[{out_v}]; "
        filter_complex += f"{prev_a}[{i}:a]acrossfade=d={crossfade_duration}[{out_a}]; "
        prev_v = f"[{out_v}]"
        prev_a = f"[{out_a}]"
        
    stitched_path = output_dir / "recovered_final_stitch.mp4"
    cmd = [
        stitcher.ffmpeg_path, "-y", *inputs,
        "-filter_complex", filter_complex.strip().rstrip(';'),
        "-map", prev_v,
        "-map", prev_a,
        "-s", "1080x1920", "-aspect", "9:16",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-shortest",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(stitched_path)
    ]
    subprocess.run(cmd, check=True)
    
    # 6. Captions
    logger.info("Step 3: Burning captions (LinkedIn Style)...")
    final_output = await burner.burn_captions(str(stitched_path), scenes_obj, "RECOVERED_PROPER_FINAL")
    
    logger.info(f"SUCCESS! Final video: {final_output}")

if __name__ == "__main__":
    asyncio.run(main())
