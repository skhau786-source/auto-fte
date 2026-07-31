import io
import uuid
import asyncio
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from huggingface_hub import InferenceClient

from app.config import settings
from app.models import GeneratedPost

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

HF_MODELS = {
    "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
    "flux": "black-forest-labs/FLUX.1-dev",  # better quality than schnell
}

hf_client = InferenceClient(provider="auto", api_key=settings.HUGGINGFACE_API_TOKEN)


IMAGES_DIR = Path("static/generated_images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


async def generate_caption(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You write short, catchy Instagram captions with relevant hashtags for e-commerce brands.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 200,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Groq API error: {resp.text}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def generate_image(prompt: str, model: str = "sdxl") -> str:
    model_id = HF_MODELS.get(model, HF_MODELS["sdxl"])

    # Add quality-boosting keywords automatically to every prompt
    enhanced_prompt = (
        f"{prompt}, high quality, ultra detailed, sharp focus, professional photography, 8k"
    )

    loop = asyncio.get_event_loop()
    try:
        image = await loop.run_in_executor(
            None,
            lambda: hf_client.text_to_image(
                enhanced_prompt,
                model=model_id,
                negative_prompt="blurry, low quality, distorted, watermark, text, deformed",
                num_inference_steps=40,   # more steps = cleaner image (default is often 20-25)
                guidance_scale=7.5,       # how strictly it follows the prompt
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Hugging Face error: {str(e)}")

    image = image.convert("RGB")
    image.thumbnail((1024, 1024))

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = IMAGES_DIR / filename
    image.save(filepath, format="JPEG", quality=95)

    return f"static/generated_images/{filename}"

async def save_generated_post(
    db: AsyncSession, student_id, prompt: str, caption: str, image_path: str, image_model: str
) -> GeneratedPost:
    post = GeneratedPost(
        student_id=student_id,
        prompt=prompt,
        caption=caption,
        image_path=image_path,
        image_model=image_model,
        status="draft",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post