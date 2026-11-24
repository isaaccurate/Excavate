import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend holds the provider key and AWS credentials, so the browser never
// talks to OpenAI or AWS directly. In development the page calls a same-origin
// /answer, and Vite forwards it to the local FastAPI server.
const target = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/answer": { target, changeOrigin: true },
      "/health": { target, changeOrigin: true },
    },
  },
});
