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

(Point this to wherever your backend runs.)

## What the Backend Needs to Build
- **Auth API** — signup/login endpoints, plus `POST /api/auth/google` (expects `email`, `name`, `picture`, `googleId`)
- **Shopify OAuth** — endpoint to exchange OAuth code for an access token
- **Inventory API** — endpoint to return real product data (currently mocked)

## Author
Laiba Jabbar — https://github.com/Laibajabbareng