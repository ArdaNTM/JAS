import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Only the local Vite proxy sees this secret; never use VITE_ variables,
// never send it to the browser, and never weaken Core's bearer validation.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const corePort = Number(process.env.AURA_CORE_PORT || env.AURA_CORE_PORT || "8000");
  const uiPort = Number(process.env.AURA_UI_PORT || env.AURA_UI_PORT || "5173");
  for (const [name, port] of [["AURA_CORE_PORT", corePort], ["AURA_UI_PORT", uiPort]] as const) {
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error(`Invalid ${name}`);
    }
  }
  const proxyTarget = `http://127.0.0.1:${corePort}`;
  const allowedOrigin = `http://127.0.0.1:${uiPort}`;
  const bearerToken = process.env.AURA_API_BEARER_TOKEN || "";

  function governedProxy(stream = false): ProxyOptions {
    return {
      target: proxyTarget,
      changeOrigin: true,
      configure: (proxyServer) => {
        proxyServer.on("proxyReq", (proxyReq) => {
          proxyReq.removeHeader("authorization");
          if (bearerToken) {
            proxyReq.setHeader("authorization", `Bearer ${bearerToken}`);
          }
        });
        if (stream) {
          proxyServer.on("proxyRes", (_proxyResponse, request, response) => {
            if (request.url?.startsWith("/api/events/stream")) {
              setImmediate(() => {
                if (!response.headersSent) response.flushHeaders();
              });
            }
          });
        }
      },
    };
  }

  const proxy = {
    // SSE connection is public only to the local app; the Kernel EventBus
    // still applies its own allowlist.
    "/api/events/stream": governedProxy(true),
    "/api": governedProxy(),
    "/v1": governedProxy(),
    "/health": governedProxy(),
    "/live": governedProxy(),
    "/ready": governedProxy(),
    "/metrics": governedProxy(),
  };

  return {
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "aura-loopback-api-guard",
        configureServer(server: import("vite").ViteDevServer) {
          server.middlewares.use((req, res, next) => {
            // Do not let another local website or DNS rebinding use the
            // privileged proxy. Header checks never replace Core auth.
            const host = req.headers.host;
            const origin = req.headers.origin;
            const fetchSite = req.headers["sec-fetch-site"];
            if (host !== `127.0.0.1:${uiPort}` ||
                (origin && origin !== allowedOrigin) ||
                fetchSite === "cross-site") {
              res.statusCode = 403;
              res.end("AURA local application origin required");
              return;
            }
            next();
          });
        },
      },
    ],
    server: {
      host: "127.0.0.1",
      port: uiPort,
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: uiPort,
      strictPort: true,
      proxy,
    },
  };
});
