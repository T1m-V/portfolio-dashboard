import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const processEnv =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env ?? {};
const apiTarget = processEnv.VITE_API_TARGET ?? processEnv.DASHBOARD_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget
    }
  }
});
