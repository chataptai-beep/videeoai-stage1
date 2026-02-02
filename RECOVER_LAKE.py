import asyncio
import logging
import os
import subprocess
import re
from pathlib import Path
from pipeline.video_stitcher import VideoStitcher
from pipeline.caption_burner import CaptionBurner
from models.schemas import Scene

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LakeRecovery")

async def main():
    stitcher = VideoStitcher()
    burner = CaptionBurner()
    output_dir = Path("outputs")
    temp_dir = Path("temp")
    
    # 1. Source scenes
    raw_scenes = [temp_dir / f"scene_{i}.mp4" for i in range(1, 4)]
    dialogues = [
        "They say you can’t mix business and pleasure.",
        "Watch me prove them wrong.",
        "I help my clients find the best homes on the lake."
    ]
    
    scenes_obj = []
    for i, d in enumerate(dialogues):
        scenes_obj.append(Scene(scene_number=i+1, visual_description="", dialogue=d, video_url=""))

    # 2. Standardize
    std_videos = []
    durations = []
    target_w, target_h = 1080, 1920
    
    for i, v in enumerate(raw_scenes):
        std_path = output_dir / f"lake_std_{i}.mp4"
        vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
              f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2,"
              f"setsar=1")
        input_args = ["-y"]
        if i > 0: input_args.extend(["-ss", "1.0"])
        input_args.extend(["-i", str(v)])
        
        cmd = [stitcher.ffmpeg_path, *input_args, "-vf", vf, "-r", "30", 
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(std_path)]
        subprocess.run(cmd, check=True)
        std_videos.append(str(std_path))
        
        # Duration
        res = subprocess.run([stitcher.ffmpeg_path, "-i", str(std_path)], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
        durations.append(float(m.group(1))*3600 + float(m.group(2))*60 + float(m.group(3)) if m else 7.0)

    # 3. Stitch
    n = len(std_videos)
    inputs = []
    for v in std_videos: inputs.extend(["-i", v])
    
    filter_complex = ""
    prev_v, prev_a = "[0:v]", "[0:a]"
    cum_offset, xfade_d = 0.0, 0.5
    for i in range(1, n):
        cum_offset += durations[i-1] - xfade_d
        out_v, out_a = f"v_f{i}", f"a_f{i}"
        filter_complex += f"{prev_v}[{i}:v]xfade=transition=fade:duration={xfade_d}:offset={cum_offset}[{out_v}]; "
        filter_complex += f"{prev_a}[{i}:a]acrossfade=d={xfade_d}[{out_a}]; "
        prev_v, prev_a = f"[{out_v}]", f"[{out_a}]"
        
    stitched_path = output_dir / "lake_final_stitch.mp4"
    cmd = [stitcher.ffmpeg_path, "-y", *inputs, "-filter_complex", filter_complex.strip().rstrip(';'),
           "-map", prev_v, "-map", prev_a, "-s", "1080x1920", "-aspect", "9:16",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-shortest",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(stitched_path)]
    subprocess.run(cmd, check=True)

    # 4. Burn Captions
    final_output = await burner.burn_captions(str(stitched_path), scenes_obj, "FINAL_LAKE_ESTATE")
    print(f"DONE: {final_output}")

if __name__ == "__main__":
    asyncio.run(main())
