import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    TanStackRouterVite({ routesDirectory: path.join(root, "src/routes") }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: { "@": path.join(root, "src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/video": "http://127.0.0.1:8765",
      "/live.jpg": "http://127.0.0.1:8765",
      "/health": "http://127.0.0.1:8765",
      "/retina": { target: "ws://127.0.0.1:8765", ws: true },
      "/media": "http://127.0.0.1:8765",
    },
  },
});
