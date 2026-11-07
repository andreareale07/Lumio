/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig(({ mode }) => {
  // Il nome prodotto arriva solo dalla config (VITE_APP_NAME), anche nel manifest.
  const appName = loadEnv(mode, process.cwd(), "VITE_").VITE_APP_NAME || "Lumio";
  return {
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // "prompt": il nuovo service worker aspetta il consenso dell'utente
      // (banner di aggiornamento) invece di ricaricare la pagina da solo.
      registerType: "prompt",
      includeAssets: ["favicon.svg", "apple-touch-icon-180x180.png"],
      manifest: {
        name: appName,
        short_name: appName,
        description: "See your money clearly.",
        lang: "it",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait",
        background_color: "#ffffff",
        theme_color: "#4F46E5",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
        shortcuts: [
          { name: "Movimenti", url: "/transactions", icons: [{ src: "pwa-192x192.png", sizes: "192x192" }] },
        ],
      },
      workbox: {
        // Si precachano solo gli asset statici della SPA. Le API (dati
        // finanziari, token) non passano MAI dalla cache del service worker.
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
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
  };
});
