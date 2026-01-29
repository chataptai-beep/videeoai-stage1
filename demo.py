import httpx
import time
import json
import sys
import asyncio

async def run_demo():
    url = "http://localhost:8000"
    prompt = "A high-tech laboratory where a professional barista robot is brewing coffee with steam and neon cinematic lighting, 4k, highly detailed"
    
    print(f"🚀 Starting Videeo.ai Demo...")
    print(f"📝 Prompt: {prompt}")
    
    # 1. Start Generation
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{url}/generate",
                json={"prompt": prompt, "scenes": 4}
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data["job_id"]
            print(f"✅ Job Created! ID: {job_id}")
        except Exception as e:
            print(f"❌ Failed to start job: {e}")
            return

        # 2. Poll Status
        print("\n⏳ Monitoring Progress (takes 2-4 minutes)...")
        last_step = ""
        while True:
            try:
                status_res = await client.get(f"{url}/status/{job_id}")
                status_res.raise_for_status()
                status = status_res.json()
                
                curr_status = status["status"]
                progress = status["progress_percent"]
                step = status["current_step"]
                
                if step != last_step:
                    print(f"📊 [{progress}%] {step}")
                    last_step = step
                    
                if curr_status == "complete":
                    print(f"\n🎉 SUCCESS! Video is ready.")
                    print(f"📁 Location: outputs/final_{job_id}_captioned.mp4")
                    break
                elif curr_status == "error":
                    print(f"\n❌ Pipeline Error: {status.get('error_message')}")
                    break
                    
                await asyncio.sleep(10)
            except Exception as e:
                print(f"⚠️ Polling error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_demo())
