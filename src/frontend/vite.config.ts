import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Proxy WebSocket first (more specific path)
      "/api/v1/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
      // Proxy REST API calls to FastAPI backend
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "ES2022",
    sourcemap: true,
    outDir: "dist",
  },
});
