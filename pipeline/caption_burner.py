"""
Caption Burner using FFmpeg.
Burns text captions into video with specified styling.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_EXE = "ffmpeg"  # Fallback to system PATH

from config import settings
from models.schemas import Scene

logger = logging.getLogger(__name__)


class CaptionBurner:
    """
    Burns captions (text overlays) into video using FFmpeg drawtext filter.
    Follows client spec: Arial Bold 48, bottom center, white with black outline.
    """
    
    def __init__(self):
        self.output_dir = Path(settings.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = FFMPEG_EXE
        logger.info(f"CaptionBurner using FFmpeg at: {self.ffmpeg_path}")
        
        # Caption styling (as per client requirements)
        self.font_family = "Arial"
        self.font_size = 48
        self.font_color = "white"
        self.outline_color = "black"
        self.outline_width = 2
        self.box_enabled = True
        self.box_color = "black@0.5"  # Semi-transparent black background
        self.box_padding = 10
    
    async def burn_captions(
        self,
        input_video_path: str,
        scenes: List[Scene],
        output_filename: str,
        scene_duration: float = 6.0
    ) -> str:
        """
        Burn captions. Uses synchronous execution for stability.
        Auto-calculates duration per scene to prevent drift.
        """
        import subprocess
        
        # 1. Determine actual duration to split captions evenly
        total_duration = await self._get_duration_async(str(input_video_path))
        if total_duration > 0 and len(scenes) > 0:
            scene_duration = total_duration / len(scenes)
            logger.info(f"Calculated dynamic scene duration: {scene_duration:.2f}s (Total: {total_duration}s, Scenes: {len(scenes)})")

        filter_complex = self._build_drawtext_filter(scenes, scene_duration)
        output_path = self.output_dir / f"{output_filename}_captioned.mp4"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_video_path),
            "-vf", filter_complex,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "copy", "-movflags", "+faststart",
            str(output_path)
        ]
        
        # Run in thread
        await asyncio.to_thread(self._run_ffmpeg_sync, cmd)
        return str(output_path)

    async def _get_duration_async(self, path: str) -> float:
        import subprocess
        def _get():
            cmd = [self.ffmpeg_path, "-i", path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            import re
            m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
            if m:
                h, m, s = map(float, m.groups())
                return h*3600 + m*60 + s
            return 0.0
        return await asyncio.to_thread(_get)

    def _run_ffmpeg_sync(self, cmd):
        import subprocess
        logger.info(f"Running FFmpeg caption burn: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    
    def _build_drawtext_filter(
        self,
        scenes: List[Scene],
        scene_duration: float
    ) -> str:
        """
        Build the FFmpeg drawtext filter string for all scenes.
        
        Each scene's dialogue is shown during that scene's duration.
        """
        if not scenes:
            return "null"  # No-op filter
        
        drawtext_filters = []
        
        for i, scene in enumerate(scenes):
            # Calculate timing for this scene
            start_time = i * scene_duration
            end_time = start_time + scene_duration
            
            # Skip empty dialogues
            if not scene.dialogue or not scene.dialogue.strip():
                continue
            
            # Escape special characters for FFmpeg
            text = self._escape_text(scene.dialogue)
            
            # On Windows, drive letter colons in fontfile path must be escaped for FFmpeg filters
            # Standard formatting: C\\:/Windows/Fonts/arialbd.ttf
            font_path = "C\\:/Windows/Fonts/arialbd.ttf"
            
            # Build drawtext filter for this scene
            # Using enable filter to show text only during scene duration
            filter_str = (
                f"drawtext="
                f"text='{text}':"
                f"fontfile='{font_path}':"
                f"fontsize={self.font_size}:"
                f"fontcolor={self.font_color}:"
                f"borderw={self.outline_width}:"
                f"bordercolor={self.outline_color}:"
                f"x=(w-text_w)/2:"  # Center horizontally
                f"y=h-th-50:"  # Bottom with 50px padding
                f"enable='between(t,{start_time},{end_time})'"
            )
            
            # Optional: Add background box
            if self.box_enabled:
                filter_str += f":box=1:boxcolor={self.box_color}:boxborderw={self.box_padding}"
            
            drawtext_filters.append(filter_str)
        
        if not drawtext_filters:
            return "null"
        
        # Chain all drawtext filters
        return ",".join(drawtext_filters)
    
    def _escape_text(self, text: str) -> str:
        """Escape special characters for FFmpeg drawtext filter."""
        # Characters that need escaping in FFmpeg drawtext
        escape_chars = {
            "'": "'\\''",  # Single quote
            ":": "\\:",    # Colon (drawtext parameter separator)
            "\\": "\\\\",  # Backslash
            "%": "\\%",    # Percent (used for variables)
            "\n": " ",     # Newline to space
        }
        
        result = text
        for char, escaped in escape_chars.items():
            result = result.replace(char, escaped)
        
        return result
    
    async def burn_captions_with_srt(
        self,
        input_video_path: str,
        scenes: List[Scene],
        output_filename: str,
        scene_duration: float = 6.0
    ) -> str:
        """
        Alternative method: Generate SRT subtitles and burn them in.
        More reliable for complex text with special characters.
        """
        # Generate SRT file
        srt_path = self._generate_srt(scenes, scene_duration)
        
        output_path = self.output_dir / f"{output_filename}_captioned.mp4"
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_video_path,
            "-vf", f"subtitles={srt_path}:force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=2,Shadow=0,Alignment=2'",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Cleanup SRT file
        try:
            os.remove(srt_path)
        except:
            pass
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"FFmpeg SRT subtitle error: {error_msg}")
            # Fall back to drawtext method
            return await self.burn_captions(
                input_video_path, scenes, output_filename, scene_duration
            )
        
        logger.info(f"Captioned video (SRT method) saved to: {output_path}")
        return str(output_path)
    
    def _generate_srt(
        self,
        scenes: List[Scene],
        scene_duration: float
    ) -> str:
        """Generate SRT subtitle file."""
        srt_path = self.output_dir / "captions.srt"
        
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, scene in enumerate(scenes):
                if not scene.dialogue or not scene.dialogue.strip():
                    continue
                
                start_time = i * scene_duration
                end_time = start_time + scene_duration
                
                # Format time as HH:MM:SS,mmm
                start_str = self._format_srt_time(start_time)
                end_str = self._format_srt_time(end_time)
                
                f.write(f"{i + 1}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{scene.dialogue}\n\n")
        
        return str(srt_path)
    
    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
