import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.DASHBOARD_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget
    }
  }
});
