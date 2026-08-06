import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Port 3000 matches the backend's CORS allowlist (backend-fte/.env
    // CORS_ORIGINS="http://localhost:3000,..."), so the browser can call the API.
    port: 3000,
    strictPort: true, // fail loudly instead of silently moving to 3001 (CORS would break)
  },
});
