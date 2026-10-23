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
    // Keep this more-specific route before /api so SSE can flush its
    // response headers immediately, even before the first event is emitted.
    "/api/events/stream": {
      target: proxyTarget,
      changeOrigin: true,
      configure: (proxyServer) => {
        proxyServer.on("proxyRes", (_proxyResponse, request, response) => {
          if (request.url?.startsWith("/api/events/stream")) {
            // http-proxy copies the upstream headers after emitting proxyRes.
            // Flush on the next event-loop turn so Content-Type is preserved.
            setImmediate(() => {
              if (!response.headersSent) {
                response.flushHeaders();
              }
            });
          }
        });
      },
    },
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
