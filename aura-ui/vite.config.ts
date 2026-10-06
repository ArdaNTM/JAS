import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const corePort =
    env.AURA_CORE_PORT ||
    process.env.AURA_CORE_PORT ||
    "8000";

  const proxyTarget =
    `http://127.0.0.1:${corePort}`;

  const proxy = {
    "/api": {
      target: proxyTarget,
      changeOrigin: true,
    },
    "/v1": {
      target: proxyTarget,
      changeOrigin: true,
    },
    "/health": {
      target: proxyTarget,
      changeOrigin: true,
    },
    "/live": {
      target: proxyTarget,
      changeOrigin: true,
    },
    "/ready": {
      target: proxyTarget,
      changeOrigin: true,
    },
    "/metrics": {
      target: proxyTarget,
      changeOrigin: true,
    },
  };

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],

    server: {
      proxy,
    },

    preview: {
      proxy,
    },
  };
});