import { defineConfig } from "vite";

/** The stdlib reader API (:8000) backs re-translate; dev and preview share it. */
const apiProxy = {
  "/api": "http://127.0.0.1:8000",
};

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: apiProxy,
  },
});
