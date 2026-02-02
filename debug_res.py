import subprocess
import re
import os

ffmpeg_path = r"C:\Users\kamra\AppData\Local\Programs\Python\Python313\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

def get_video_info(path):
    cmd = [ffmpeg_path, "-i", path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    for line in res.stderr.split("\n"):
        if "Video:" in line:
            match = re.search(r", (\d{3,4})x(\d{3,4})", line)
            if match:
                return f"{match.group(1)}x{match.group(2)}"
            return line.strip()
    return "Not found"

for i in range(6):
    path = f"outputs/std_scene_{i}.mp4"
    if os.path.exists(path):
        print(f"{path}: {get_video_info(path)}")
    else:
        print(f"{path} missing")
