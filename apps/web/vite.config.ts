import fs from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";

/** The stdlib reader API (:8000) backs re-translate; dev and preview share it. */
const apiProxy = {
  "/api": "http://127.0.0.1:8000",
};

function contentTypeFor(file: string): string {
  if (file.endsWith(".json")) return "application/json; charset=utf-8";
  if (file.endsWith(".pdf")) return "application/pdf";
  return "application/octet-stream";
}

/**
 * Serve `/data/*` from `public/data` on every request.
 *
 * Retranslate publishes `revisions/<id>/` after the Vite process starts. The
 * default SPA fallback would otherwise return `index.html` (200) for those
 * paths, and the reader would try to parse HTML as mapping JSON.
 */
function servePublicData(): Plugin {
  const send = (req: IncomingMessage, res: ServerResponse, publicDir: string): boolean => {
    const rawPath = (req.url ?? "").split("?")[0] ?? "";
    if (!rawPath.startsWith("/data/")) return false;
    let decoded: string;
    try {
      decoded = decodeURIComponent(rawPath);
    } catch {
      res.statusCode = 400;
      res.end();
      return true;
    }
    const dataRoot = path.resolve(publicDir, "data");
    const file = path.resolve(publicDir, decoded.slice(1));
    const relative = path.relative(dataRoot, file);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      res.statusCode = 403;
      res.end();
      return true;
    }
    let stat: fs.Stats;
    try {
      stat = fs.statSync(file);
    } catch {
      res.statusCode = 404;
      res.setHeader("content-type", "text/plain; charset=utf-8");
      res.end("not found");
      return true;
    }
    if (!stat.isFile()) {
      res.statusCode = 404;
      res.setHeader("content-type", "text/plain; charset=utf-8");
      res.end("not found");
      return true;
    }
    res.statusCode = 200;
    res.setHeader("content-type", contentTypeFor(file));
    res.setHeader("content-length", String(stat.size));
    if (req.method === "HEAD") {
      res.end();
      return true;
    }
    fs.createReadStream(file).pipe(res);
    return true;
  };

  return {
    name: "serve-public-data",
    configureServer(server) {
      const publicDir = path.resolve(server.config.root, "public");
      server.middlewares.use((req, res, next) => {
        if (!send(req, res, publicDir)) next();
      });
    },
    configurePreviewServer(server) {
      const publicDir = path.resolve(server.config.root, "public");
      server.middlewares.use((req, res, next) => {
        if (!send(req, res, publicDir)) next();
      });
    },
  };
}

export default defineConfig({
  plugins: [servePublicData()],
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
