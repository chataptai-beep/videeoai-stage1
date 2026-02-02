import subprocess
import re
import os

ffmpeg_path = r"C:\Users\kamra\AppData\Local\Programs\Python\Python313\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

def get_duration(path):
    cmd = [ffmpeg_path, "-i", path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
    if match:
        h, m, s = map(float, match.groups())
        return h*3600 + m*60 + s
    return 0

for i in range(1, 7):
    path = f"temp/scene_{i}.mp4"
    if os.path.exists(path):
        print(f"{path}: {get_duration(path)}s")
    else:
        print(f"{path} missing")
