import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API_HOST = process.env.VITE_API_HOST || "localhost";
const API_PORT = process.env.VITE_API_PORT || "8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://${API_HOST}:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
  define: {
    __API_HOST__: JSON.stringify(API_HOST),
    __API_PORT__: JSON.stringify(API_PORT),
  },
});
