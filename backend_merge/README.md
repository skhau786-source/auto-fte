# Digital FTE Backend

FastAPI backend for Digital FTE agent (Shopify integration + inventory + social media automation).

## Run
pip install -r requirements.txt
uvicorn app.main:app --reload

## Login / Auth
JWT-based login system. Register/login karke `access_token` milta hai, jo
har protected route ke `Authorization: Bearer <token>` header me bhejna hota hai.

| Method | Endpoint          | Purpose                                        |
|--------|-------------------|------------------------------------------------|
| POST   | `/auth/signup`    | Naya user banao (username + email + password)  |
| POST   | `/auth/login`     | Login karo (token milta hai)                   |
| POST   | `/auth/google`    | Google Sign-In id_token se login               |
| GET    | `/auth/me`        | Current user ki details                        |
| POST   | `/auth/send-verification` | Email verification link bhejta hai      |
| GET    | `/auth/verify-email` | Email verify karo (`?token=...`)            |
| POST   | `/auth/forgot-password` | Password reset link email par            |
| POST   | `/auth/reset-password` | Naya password set karo (`token + new_password`) |

Login par brute-force protection hai (rate limiting - har IP par 15 min me max 5 attempts, 6th attempt par 429).
Email verification aur password reset ke liye `.env` me SMTP settings zaroori hain
(`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `FRONTEND_URL`).

Signup password me at least 1 digit aur 1 uppercase letter zaroori hai.
`.env` me `SECRET_KEY` set karna zaroori hai (production me strong value),
Google login ke liye `GOOGLE_CLIENT_ID` bhi chahiye.

Har store (Shopify/WooCommerce) ab ek user ke account me save hota hai
(`user_id`), aur store/product routes sirf us user ke apne stores dikhate hain.

## Inventory
Login ke baad store connect karo (Shopify ya WooCommerce), phir inventory
endpoints us connected store ke products + stock levels dikhate hain.
Har call pehle store API se taza data sync karta hai (store unreachable ho to
DB ka purana data + `sync_error` message deta hai - kabhi hang nahi hota).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/inventory` | Connected store ka product inventory (search, low-stock filter, pagination) |
| GET | `/inventory/low-stock` | Kam stock wale items (`?threshold=10`) |
| GET | `/inventory/summary` | Dashboard: total / in-stock / low-stock / out-of-stock |
| GET | `/shopify/synced-products?shop=...` | Shopify store ke DB me save products |
| GET | `/woocommerce/synced-products?store_url=...` | WooCommerce store ke DB me save products |

`shop` (Shopify domain) ya `store_url` (WooCommerce URL) optional hain - bina
diye user ka pehla connected store apne aap select hota hai.

Inventory module team member ke repo (`backend-fte/app/inventory/`) ke design
se merge kiya gaya hai - unka pura system async + UUID + warehouses/reservations
par bana hai, isliye iska core (product list + low-stock + summary) yahan sync
architecture me adapt kiya gaya hai.
