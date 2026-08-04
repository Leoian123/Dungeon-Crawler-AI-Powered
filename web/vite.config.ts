import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev: la SPA gira su Vite (5173) e inoltra /api all'host web FastAPI (8017,
// avviato da gioca_web.bat). Stessa origine ⇒ niente CORS. `ws: false` e niente
// buffering: gli SSE passano così come sono. `DCC_API_PORT` sposta il target
// del proxy quando l'host gira su una porta alternativa (`--porta N`).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.DCC_API_PORT ?? "8017"}`,
        changeOrigin: true,
      },
    },
  },
});
