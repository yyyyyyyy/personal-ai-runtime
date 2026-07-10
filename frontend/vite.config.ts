import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const API_HOST = process.env.VITE_API_HOST || "localhost";
const API_PORT = process.env.VITE_API_PORT || "8000";
const isDesktopBuild = process.env.VITE_DESKTOP === "1";

export default defineConfig({
  // Read VITE_* from repo-root .env (same file as backend AUTH_TOKEN)
  envDir: rootDir,
  base: isDesktopBuild ? "./" : "/",
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
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (
              id.includes("react-markdown") ||
              id.includes("remark-") ||
              id.includes("micromark") ||
              id.includes("mdast") ||
              id.includes("unist")
            ) {
              return "vendor-markdown";
            }
            if (
              id.includes("react-dom") ||
              id.includes("react-router") ||
              id.includes("/react/")
            ) {
              return "vendor-react";
            }
            if (id.includes("react-syntax-highlighter") || id.includes("refractor")) {
              // Leave syntax highlighter in async chunks (lazy-loaded via CodeBlock)
              return undefined;
            }
            if (id.includes("lucide-react")) {
              return "vendor-icons";
            }
            return "vendor";
          }
          if (id.includes("/src/pages/")) {
            const page = id.split("/src/pages/")[1]?.split(".")[0];
            if (page) return `page-${page.replace(/Page$/, "").toLowerCase()}`;
          }
        },
      },
    },
  },
});
