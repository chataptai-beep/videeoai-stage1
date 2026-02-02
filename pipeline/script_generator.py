"""
Script Generator using OpenAI GPT-4o-mini.
Generates structured 5-scene video scripts from text prompts.
"""

import json
import logging
from typing import Optional

import httpx

from config import settings
from models.schemas import Scene, VideoScript

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """
    Generates video scripts using OpenAI's GPT-4o-mini.
    Produces structured JSON output with character description and scenes.
    """
    
    def _get_system_prompt(self, scene_count: int) -> str:
        """Generate high-quality viral reel script based on user prompt."""
        return f"""You are a master creative director for viral short-form content.
Your task is to create EXACTLY {scene_count} scenes based on the user's provided concept.

CRITICAL DIRECTIVES:
- **Visual Style**: Cinematic, high-fidelity, professional lighting (Golden hour, soft bokeh, lens flares).
- **Format**: Vertical 9:16 (1080x1920).
- **Pacing**: Fast-paced, high energy, no static shots.
- **Dialogue**: Break the user's script into natural segments. Ensure dialogue is punchy.
- **Character Consistency**: Describe the character's clothing and appearance in EVERY scene to ensure AI consistency.

Output ONLY valid JSON in this exact format:
{{
  "character_description": "Detailed description of the protagonist(s) for consistency.",
  "visual_style": "Detailed cinematic style guide (e.g., 35mm, f1.8, golden hour).",
  "background_theme": "Overall setting description.",
  "scenes": [
    {{
      "scene_number": 1,
      "visual_description": "Concrete action/movement, specific lighting, character clothing detail.",
      "dialogue": "Punchy, short dialogue or caption text."
    }}
  ]
}}
"""


    def __init__(self):
        self.api_key = settings.openai_api_key
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    async def generate(
        self,
        prompt: str,
        scene_count: int = 5
    ) -> VideoScript:
        """
        Generate a video script from a text prompt.
        
        Args:
            prompt: User's text prompt describing the video
            scene_count: Number of scenes to generate (default 5)
        
        Returns:
            VideoScript object with character description and scenes
        
        Raises:
            Exception: If API call fails or response is invalid
        """
        user_prompt = f"""Create a {scene_count}-scene video script for:

"{prompt}"

Make it viral-worthy, visually stunning, and perfect for social media.
Remember: You MUST output EXACTLY {scene_count} scenes. Output ONLY valid JSON, no markdown, no code blocks."""

        logger.info(f"Generating script for prompt: {prompt[:50]}...")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": self._get_system_prompt(scene_count)},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "response_format": {"type": "json_object"}
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract content from response
                content = data["choices"][0]["message"]["content"]
                script_data = json.loads(content)
                
                # Parse into VideoScript model
                scenes = [
                    Scene(
                        scene_number=s["scene_number"],
                        visual_description=s["visual_description"],
                        dialogue=s["dialogue"]
                    )
                    for s in script_data["scenes"]
                ]
                
                script = VideoScript(
                    character_description=script_data["character_description"],
                    scenes=scenes,
                    visual_style=script_data.get("visual_style"),
                    background_theme=script_data.get("background_theme")
                )
                
                logger.info(f"Generated script with {len(scenes)} scenes")
                return script
                
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Script generation failed: {e.response.status_code}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse script JSON: {e}")
            raise Exception("Failed to parse script response")
        except KeyError as e:
            logger.error(f"Missing key in script response: {e}")
            raise Exception(f"Invalid script response: missing {e}")
    
    async def generate_image_prompt(
        self,
        character_description: str
    ) -> dict:
        """
        Generate an optimized image prompt for the reference character image.
        
        Args:
            character_description: Description of the main character
        
        Returns:
            Dict with 'image_prompt' and 'negative_prompt' keys
        """
        system_prompt = """You are an elite visual prompt writer. Generate ONE portrait reference image prompt for a single subject.

The goal is character/style consistency for video generation.

Hard requirements:
- Single person only, waist-up, centered, neutral studio pose, friendly expression
- Plain seamless white studio background (#FFFFFF), no gradients, no shadows on backdrop
- No text, no logos, no icons, no UI, no watermark
- No collage/multi-panel/grid/frames
- No devices or screens (no laptop/phone/tablet)
- Natural, soft front key light, minimal fill, clean color

Output JSON only: { "image_prompt": "string", "negative_prompt": "string" }"""

        user_prompt = f"""Create a reference image prompt for this character:

{character_description}

Make it hyper-realistic, 4K, with detailed textures and consistent lighting.
Output ONLY valid JSON."""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.5,
                        "max_tokens": 500,
                        "response_format": {"type": "json_object"}
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                return json.loads(content)
                
        except Exception as e:
            logger.error(f"Failed to generate image prompt: {e}")
            # Return a sensible default
            return {
                "image_prompt": f"Professional portrait photo, {character_description}, waist-up, centered, white studio background, soft lighting, 4K, hyper-realistic",
                "negative_prompt": "text, watermark, logo, blurry, distorted, multiple people"
            }
