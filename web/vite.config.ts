import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev: Vite serves the SPA and proxies /api to the local FastAPI server.
// Prod: `npm run build` emits web/dist, which FastAPI serves directly.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
