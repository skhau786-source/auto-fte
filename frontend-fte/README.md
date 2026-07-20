# Digital FTE — Frontend

AI-powered E-commerce Autonomous Employee platform. Frontend built with Next.js + TypeScript + Tailwind CSS. Currently runs on mock/simulated data — no backend connected yet.

## Run Locally

```bash
git clone https://github.com/HassanAliJunejo/Digital-Fte-Startup.git
cd Digital-Fte-Startup
npm install
npm run dev
```
Opens at `http://localhost:3000`.

## Environment Variables
Create a `.env` file in the project root:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_oauth_client_id
```
- `NEXT_PUBLIC_API_URL` — point this to wherever your backend runs.
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — **required**, the app will crash on load without it (used in `app/layout.tsx` to initialize Google login). Get one from [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create OAuth Client ID. A placeholder value works to stop the crash if you're not testing Google login yet.

## What the Backend Needs to Build
- **Auth API** — signup/login endpoints, plus `POST /api/auth/google` (expects `email`, `name`, `picture`, `googleId`)
- **Shopify OAuth** — endpoint to exchange OAuth code for an access token
- **Inventory API** — endpoint to return real product data (currently mocked)
## Author
Laiba Jabbar — https://github.com/Laibajabbareng
