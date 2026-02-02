# Videeo.ai Stage 1 Pipeline

A production-quality FastAPI backend that converts text prompts into multi-scene, AI-generated videos with captions.

## 🚀 Features

- **Multi-Scene Generation**: Automatically converts a single prompt into a structured 5-scene script.
- **Viral-Optimized Format**: Defaulted to **Vertical (9:16)** for TikTok, Reels, and Shorts impact.
- **High-Energy Pacing**: Implements **2x Speedup (Energy Boost)** to compress scenes into punchy 4-second viral clips.
- **AI-Native Video**: Uses `kie.ai` (Veo 3 Fast) to generate consistent video scenes with natural motion.
- **Character Consistency**: Generates a reference character image first to maintain visual continuity.
- **Automated Assembly**: Stitches scenes with smooth transitions and burns in high-impact captions.
- **Hormozi-Style Captions**: Bold, yellow, large, and centered captions designed to stop the scroll.
- **Windows Optimized**: Robust path handling and dynamic FFmpeg/ffprobe detection.

---

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.10+
- FFmpeg (The app will attempt to use `imageio-ffmpeg` to handle this automatically).

### 2. Installation
```bash
# Clone the repository
git clone [your-repo-url]
cd videeo-stage1

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and add your API keys:
```bash
cp .env.example .env
```
Key variables:
- `OPENAI_API_KEY`: For script generation (GPT-4).
- `KIE_API_KEY`: For high-quality image and video generation.

---

## 📖 Usage Example

### Start the Server
```bash
python -m uvicorn main:app --reload
```

### Generate a Video
```bash
curl -X POST "http://localhost:8000/generate" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "A futuristic city with flying cars and neon lights", "scenes": 5}'
```

### Check Status
```bash
curl http://localhost:8000/status/{job_id}
```

### Download Result
```bash
curl http://localhost:8000/download/{job_id}
```

---

## 🏗️ Architecture Notes

### Pipeline Flow
1. **LLM Scripting**: GPT-4 breaks the prompt into 5 scenes with dialogue.
2. **Reference Image**: Generates a character reference using Nano Banana for consistency.
3. **Video Synthesis**: Generates individual videos per scene using Veo 3 Fast (cost-efficient and high quality).
4. **Stitching**: Uses FFmpeg with vertical scale/crop logic and **2x Speed factor** to create high-velocity transitions.
5. **Captioning**: Burns text using `drawtext` with Large Yellow Bold styling centered on screen for viral readability.

### Design Decisions
- **AI-Native Motion**: Instead of applying a basic "Ken Burns" effect to static images, the pipeline uses real AI video generation. This results in far more engaging content that captures actual movements (e.g., waves crashing, cars flying).
- **FFmpeg Lifecycle**: We use `imageio-ffmpeg` to ensure the correct binary exists in the deployment environment without manual system installation.
- **Validation-First**: Every FFmpeg call includes existence checks for fonts and input files to avoid "silent failures."

---

## ⚖️ Known Limitations & Improvements
- **In-Memory Store**: Currently uses a Python dictionary for job state. For production, this should move to Redis/PostgreSQL.
- **Cloudinary Fallback**: If Cloudinary keys aren't provided, it serves files locally.
- **Frame Continuity**: The pipeline currently uses a consistent character reference; next version should extract the last frame of scene N as the first frame for scene N+1.

---

## ⏱️ Time Spent
- **Architecture & API Setup**: 2 hours
- **Video Generation Pipeline**: 4 hours
- **FFmpeg Debugging & Path Issues**: 3 hours
- **Polishing & Documentation**: 1 hour
- **Total**: ~10 hours
