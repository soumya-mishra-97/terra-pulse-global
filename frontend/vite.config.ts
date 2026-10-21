import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = process.env.VITE_API_PROXY ?? "http://localhost:8000";

// Keep API requests and FastAPI's interactive docs (Swagger, ReDoc, OpenAPI) on the frontend origin in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(["/api", "/docs", "/redoc", "/openapi.json"].map((path) => [path, { target: API, changeOrigin: true }])),
  },
  test: { environment: "node" },
});
