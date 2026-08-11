/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // Stesso-origine anche in dev (niente CORS da configurare lato backend,
    // e il cookie httpOnly di refresh resta same-site) — in produzione lo
    // stesso ruolo lo fa nginx (vedi frontend/nginx.conf).
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
