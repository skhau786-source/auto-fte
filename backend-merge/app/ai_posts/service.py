import uuid
import asyncio
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from huggingface_hub import InferenceClient

from app.config import settings
from app.models import GeneratedPost, BrandProfile

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

HF_MODELS = {
    "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
    "flux": "black-forest-labs/FLUX.1-dev",
}

hf_client = InferenceClient(provider="auto", api_key=settings.HUGGINGFACE_API_TOKEN)

IMAGES_DIR = Path("static/generated_images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def build_brand_system_prompt(profile: BrandProfile | None) -> str:
    base_sys = "You write short, catchy, high-converting Instagram captions with relevant hashtags for e-commerce brands."
    if not profile:
        return base_sys

    details = [f"Brand Tone: {profile.tone}"]
    if profile.target_audience:
        details.append(f"Target Audience: {profile.target_audience}")
    if profile.emoji_preference:
        details.append(f"Emoji Usage Preference: {profile.emoji_preference}")
    if profile.sample_captions:
        details.append(f"Sample Captions to match style:\n{profile.sample_captions}")
    if profile.prohibited_words:
        details.append(f"PROHIBITED WORDS (NEVER USE): {profile.prohibited_words}")

    return f"{base_sys}\nFollow these specific brand guidelines:\n" + "\n".join(details)


async def generate_caption(prompt: str, system_prompt: str | None = None) -> str:
    default_sys = "You write short, catchy Instagram captions with relevant hashtags for e-commerce brands."
    sys_content = system_prompt if system_prompt else default_sys

    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 250,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Groq API error: {resp.text}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def generate_image(prompt: str, model: str = "sdxl", aspect_ratio: str = "1:1", style_preset: str | None = None) -> str:
    model_id = HF_MODELS.get(model, HF_MODELS["sdxl"])

    dimensions = {
        "1:1": (1024, 1024),
        "9:16": (768, 1344),
        "4:5": (896, 1120),
    }
    target_width, target_height = dimensions.get(aspect_ratio, (1024, 1024))

    style_suffix = f", {style_preset} style" if style_preset else ""
    enhanced_prompt = (
        f"{prompt}{style_suffix}, high quality, ultra detailed, sharp focus, professional photography, 8k"
    )

    loop = asyncio.get_event_loop()
    try:
        image = await loop.run_in_executor(
            None,
            lambda: hf_client.text_to_image(
                enhanced_prompt,
                model=model_id,
                negative_prompt="blurry, low quality, distorted, watermark, text, deformed",
                num_inference_steps=40,
                guidance_scale=7.5,
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Hugging Face error: {str(e)}")

    image = image.convert("RGB")
    image = image.resize((target_width, target_height))

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = IMAGES_DIR / filename
    image.save(filepath, format="JPEG", quality=95)

    return f"static/generated_images/{filename}"


async def save_generated_post(
    db: AsyncSession, student_id: uuid.UUID, prompt: str, caption: str, image_path: str, image_model: str, aspect_ratio: str = "1:1"
) -> GeneratedPost:
    post = GeneratedPost(
        student_id=student_id,
        prompt=prompt,
        caption=caption,
        image_path=image_path,
        image_model=image_model,
        aspect_ratio=aspect_ratio,
        status="draft",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post
