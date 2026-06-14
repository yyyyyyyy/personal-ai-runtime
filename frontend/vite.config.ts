import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const API_HOST = process.env.VITE_API_HOST || "localhost";
const API_PORT = process.env.VITE_API_PORT || "8000";

export default defineConfig({
  // Read VITE_* from repo-root .env (same file as backend AUTH_TOKEN)
  envDir: rootDir,
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://${API_HOST}:${API_PORT}`,
        changeOrigin: true,
      },
      "/ws": {
        target: `http://${API_HOST}:${API_PORT}`,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  define: {
    __API_HOST__: JSON.stringify(API_HOST),
    __API_PORT__: JSON.stringify(API_PORT),
  },
});
