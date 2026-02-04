"""
Video Stitcher using FFmpeg.
Combines multiple scene videos into a single output with transitions.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

import httpx

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_EXE = "ffmpeg"  # Fallback to system PATH

from config import settings

logger = logging.getLogger(__name__)


class VideoStitcher:
    """
    Stitches multiple video clips into a single video using FFmpeg.
    Supports crossfade transitions and trim operations.
    """
    
    def __init__(self):
        self.temp_dir = Path(settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(settings.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = FFMPEG_EXE
        logger.info(f"Using FFmpeg at: {self.ffmpeg_path}")
    
    async def stitch_videos(
        self,
        video_urls: List[str],
        output_filename: str,
        crossfade_duration: float = 0.5,
        trim_start_scenes_2_plus: float = 0.5
    ) -> str:
        """
        Stitch multiple video URLs into a single video.
        
        Args:
            video_urls: List of video URLs to stitch
            output_filename: Name for the output file (without extension)
            crossfade_duration: Duration of crossfade transitions in seconds
            trim_start_scenes_2_plus: Seconds to trim from start of scenes 2+ (for continuity)
        
        Returns:
            Path to the stitched video file
        
        Raises:
            Exception: If stitching fails
        """
        if not video_urls:
            raise Exception("No videos to stitch")
        
        if len(video_urls) == 1:
            # Single video, just download and return
            local_path = await self._download_video(video_urls[0], "scene_1.mp4")
            output_path = self.output_dir / f"{output_filename}.mp4"
            os.rename(local_path, output_path)
            return str(output_path)
        
        logger.info(f"Stitching {len(video_urls)} videos...")
        
        # Step 1: Download all videos
        local_videos = []
        for i, url in enumerate(video_urls):
            local_path = await self._download_video(url, f"scene_{i + 1}.mp4")
            local_videos.append(local_path)
        
        # Step 2: Create FFmpeg concat file
        concat_file = self._create_concat_file(local_videos, trim_start_scenes_2_plus)
        
        # Step 3: Run FFmpeg to stitch
        output_path = self.output_dir / f"{output_filename}.mp4"
        await self._run_ffmpeg_concat(concat_file, str(output_path), crossfade_duration)
        
        # Step 4: Cleanup temp files
        self._cleanup_temp_files(local_videos + [concat_file])
        
        logger.info(f"Stitched video saved to: {output_path}")
        return str(output_path)
    
    async def _download_video(self, url: str, filename: str) -> str:
        """Download a video from URL to temp directory."""
        local_path = self.temp_dir / filename
        
        logger.debug(f"Downloading video: {url}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            with open(local_path, "wb") as f:
                f.write(response.content)
        
        return str(local_path)
    
    def _create_concat_file(
        self,
        video_paths: List[str],
        trim_start_seconds: float = 0.0
    ) -> str:
        """Create a concat demuxer file for FFmpeg."""
        concat_path = self.temp_dir / "concat.txt"
        
        with open(concat_path, "w") as f:
            for i, video_path in enumerate(video_paths):
                # Use absolute paths to avoid FFmpeg path resolution issues
                abs_path = os.path.abspath(video_path)
                # Escape single quotes in path for FFmpeg and use forward slashes
                escaped_path = abs_path.replace("\\", "/").replace("'", "'\\''")
                
                # For scenes 2+, we might want to trim the start
                # to avoid duplicate frames from continuity
                if i > 0 and trim_start_seconds > 0:
                    # We'll handle trimming in the filter complex instead
                    pass
                
                f.write(f"file '{escaped_path}'\n")
        
        return str(concat_path)
    
    async def _run_ffmpeg_concat(
        self,
        concat_file: str,
        output_path: str,
        crossfade_duration: float = 0.5
    ):
        """Run FFmpeg to concatenate videos."""
        
        # Simple concat without complex transitions
        # For MVP, use basic concatenation
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ]
        
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"FFmpeg error: {error_msg}")
            raise Exception(f"FFmpeg concat failed: {error_msg[:200]}")
        
        logger.info("FFmpeg concat completed successfully")
    
    async def stitch_with_crossfade(
        self,
        video_urls: List[str],
        output_filename: str,
        crossfade_duration: float = 1.0
    ) -> str:
        # 1. Download Async
        local_videos = []
        for i, url in enumerate(video_urls):
             # Ensure we get the duration
            path = await self._download_video(url, f"scene_{i+1}.mp4")
            local_videos.append(path)

        # 2. Run FFmpeg Heavy Lifting in Thread
        return await asyncio.to_thread(
            self._process_ffmpeg_sync,
            local_videos,
            output_filename,
            crossfade_duration
        )

    def _process_ffmpeg_sync(self, local_videos, output_filename, crossfade_duration):
        import subprocess
        from config import settings
        # Get Durations & Speed Up Factor
        # User Request: Don't apply 2x speed. Use native speed.
        speed_factor = 1.0
        
        # Standardize (Vertical Crop + Speed Up)
        std_videos = []
        durations = [] # We will calculate durations of the processed videos
        target_w = settings.video_width
        target_h = settings.video_height
        
        for i, v in enumerate(local_videos):
            std_path = str(self.output_dir / f"std_scene_{i}.mp4")
            
            # VF chain:
            # 1. Scale to fill target (1080x1920) while preserving aspect ratio
            # 2. Crop to exactly 1080x1920 (center)
            # 3. Force SAR 1:1 to avoid aspect ratio weirdness in players
            
            vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                  f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2,"
                  f"setsar=1")

            input_args = ["-y"]
            
            # TRIM Logic: Cut first 1s for scenes > 0 (to remove static reference frame)
            if i > 0:
                input_args.extend(["-ss", "1.0"])
            
            input_args.extend(["-i", v])

            cmd = [
                self.ffmpeg_path, *input_args,
                "-vf", vf,
                "-r", "30", # Force 30fps output
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", # Re-encode audio to AAC to ensure compatibility
                std_path
            ]
            
            subprocess.run(cmd, check=True)
            std_videos.append(std_path)
            
            # Now get the duration of the standardized video
            cmd_dur = [self.ffmpeg_path, "-i", std_path]
            res_dur = subprocess.run(cmd_dur, capture_output=True, text=True)
            import re
            match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res_dur.stderr)
            if match:
                 h, m, s = map(float, match.groups())
                 durations.append(h*3600 + m*60 + s)
            else:
                 durations.append(4.0) # Fallback
            
        # Stitch
        output_path = self.output_dir / f"{output_filename}.mp4"
        n = len(std_videos)
        
        if n == 1:
            if os.path.exists(output_path): os.remove(output_path)
            os.rename(std_videos[0], output_path)
            return str(output_path)

        inputs = []
        for v in std_videos:
            inputs.extend(["-i", v])

        # REMOVED Silent Audio Input

        # Dynamic Offsets
        filter_complex = ""
        prev_v = "[0:v]"
        prev_a = "[0:a]" # Audio is BACK
        cumulative_offset = 0.0
        
        for i in range(1, n):
            cumulative_offset += durations[i-1] - crossfade_duration
            out_v = f"v_fade_{i}"
            out_a = f"a_fade_{i}"
            filter_complex += f"{prev_v}[{i}:v]xfade=transition=fade:duration={crossfade_duration}:offset={cumulative_offset}[{out_v}]; "
            filter_complex += f"{prev_a}[{i}:a]acrossfade=d={crossfade_duration}[{out_a}]; "
            prev_v = f"[{out_v}]"
            prev_a = f"[{out_a}]"

        cmd = [
            self.ffmpeg_path, "-y", *inputs,
            "-filter_complex", filter_complex.strip().rstrip(';'),
             "-map", prev_v, 
            "-map", prev_a, # Map actual audio
            "-s", f"{target_w}x{target_h}", # FORCE VERTICAL
            "-aspect", "9:16",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-shortest", 
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(output_path)
        ]
        
        logger.info(f"Running synchronous stitching (Vertical + Fast) for {n} clips...")
        subprocess.run(cmd, check=True)
        
        # Cleanup
        # for f in local_videos + std_videos:
        #     if os.path.exists(f): os.remove(f)
            
        return str(output_path), durations
    
    def _cleanup_temp_files(self, files: List[str]):
        """Remove temporary files."""
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {file_path}: {e}")
    
    async def get_video_duration(self, video_path: str) -> float:
        """Get the duration of a video in seconds."""
        # Try ffprobe first (if it exists)
        ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        if os.path.exists(ffprobe_path) or ffprobe_path == "ffprobe":
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await process.communicate()
                if process.returncode == 0 and stdout:
                    return float(stdout.decode().strip())
            except Exception as e:
                logger.debug(f"ffprobe failed: {e}")

        # Fallback: Use ffmpeg -i
        cmd = [self.ffmpeg_path, "-i", video_path]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            output = stderr.decode()
            # Look for "Duration: 00:00:05.50"
            import re
            match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", output)
            if match:
                h, m, s = match.groups()
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception as e:
            logger.error(f"Failed to get video duration: {e}")
        
        return 0.0
