import asyncio
import os
import subprocess
import json
from pathlib import Path

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    FFPROBE_EXE = FFMPEG_EXE.replace("ffmpeg", "ffprobe")
except ImportError:
    FFMPEG_EXE = "ffmpeg"
    FFPROBE_EXE = "ffprobe"

async def get_info(path):
    cmd = [
        FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration:stream=width,height,display_aspect_ratio",
        "-of", "json", path
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode == 0:
        return json.loads(stdout)
    return {"error": stderr.decode()}

async def main():
    files = [f"outputs/std_scene_{i}.mp4" for i in range(6)]
    for f in files:
        if os.path.exists(f):
            info = await get_info(f)
            duration = info.get("format", {}).get("duration")
            vstream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
            w = vstream.get("width")
            h = vstream.get("height")
            print(f"{f}: {duration}s, {w}x{h}")
        else:
            print(f"{f} missing")

if __name__ == "__main__":
    asyncio.run(main())
