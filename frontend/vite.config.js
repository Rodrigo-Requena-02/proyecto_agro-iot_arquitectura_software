import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El proxy evita CORS en desarrollo: el navegador llama a /api y Vite lo reenvía al backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
  // `npm run preview` sirve el build de producción (donde se activa el Service Worker).
  preview: {
    port: 4173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
