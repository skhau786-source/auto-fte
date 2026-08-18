import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routes import ai_posts, auth, instagram, inventory, shopify, woocommerce

Base.metadata.create_all(bind=engine)

os.makedirs("static/generated_images", exist_ok=True)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(shopify.router)
app.include_router(woocommerce.router)
app.include_router(inventory.router)
app.include_router(ai_posts.router)
app.include_router(instagram.router)



@app.get("/")
def root(request: Request):
    """
    Jab Shopify embedded app ko load karta hai, ye root route
    id_token + shop query params ke sath call hota hai. Agar wo
    params maujood hain, hum unhe /shopify/session-auth pe forward
    kar dete hain (jo token exchange kar ke access_token save karta hai).
    Agar id_token/shop nahi hain (jaise koi seedha "/" browse kare),
    to normal health-check message dikhta hai.
    """
    id_token = request.query_params.get("id_token")
    shop = request.query_params.get("shop")
    user_id = request.query_params.get("user_id")

    if not user_id:
        user_id = "1"  # TEMPORARY: frontend banne tak fallback, Step 1 wala user_id

    if id_token and shop:
        url = f"/shopify/session-auth?shop={shop}&id_token={id_token}"
        if user_id:
            url += f"&user_id={user_id}"
        return RedirectResponse(url=url)

    return {"message": "Digital FTE backend running"}
