import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy API calls to the local FastAPI on 127.0.0.1:8765. Build output is served by the API itself.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_DEMO === "true" ? "/app/" : "/",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
});
