import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev-сервер проксирует /api в backend: тот же origin, что и за nginx, поэтому CORS не нужен.
const apiTarget = process.env.JOBRADAR_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": apiTarget },
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
