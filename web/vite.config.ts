import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // Dev server talks to the FastAPI backend directly, so the browser sees one
    // origin and EventSource needs no CORS handling.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    // FastAPI serves the built bundle, so one service and one port in Docker.
    outDir: "../static/app",
    emptyOutDir: true,
  },
})
