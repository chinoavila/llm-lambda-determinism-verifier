import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Ver docs/ui.md. En producción la SPA la sirve `python -m pipeline serve`; en
// desarrollo, `npm run dev` reenvía /api a ese mismo servidor.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: { "/api": process.env.API_URL ?? "http://localhost:8000" },
  },
  test: { environment: "node" },
});
