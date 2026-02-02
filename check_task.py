import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check():
    api_key = os.getenv("KIE_API_KEY")
    base_url = "https://api.kie.ai/api/v1/veo"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    endpoints = ["tasks", "history", "generations", "record-list", "list"]
    
    async with httpx.AsyncClient() as client:
        for ep in endpoints:
            url = f"{base_url}/{ep}"
            print(f"Trying {url}...")
            try:
                response = await client.get(url, headers=headers)
                print(f"Status: {response.status_code}")
                if response.status_code == 200:
                    print(f"BODY: {response.text[:500]}")
            except Exception as e:
                print(e)

if __name__ == "__main__":
    import asyncio
    asyncio.run(check())
