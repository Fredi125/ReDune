import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync } from "node:fs";
import { resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";

// The repo's gamedata lives one level up from web/. Serve it at /game/<name>
// during `vite dev` so the "Load sample" buttons work in any clone (no symlink).
const here = fileURLToPath(new URL(".", import.meta.url));
const gamedataDir = resolve(here, "..", "gamedata");

function serveGamedata() {
  return {
    name: "redune-serve-gamedata",
    configureServer(server: { middlewares: { use: (fn: (req: any, res: any, next: () => void) => void) => void } }) {
      server.middlewares.use((req, res, next) => {
        const url: string = req.url || "";
        if (!url.startsWith("/game/")) return next();
        const name = basename(decodeURIComponent(url.slice("/game/".length).split("?")[0]));
        const file = resolve(gamedataDir, name);
        // Only serve real files inside gamedata/ (no path traversal).
        if (!file.startsWith(gamedataDir) || !existsSync(file) || !statSync(file).isFile()) {
          res.statusCode = 404;
          res.setHeader("Content-Type", "text/plain");
          res.end("not found");
          return;
        }
        res.statusCode = 200;
        res.setHeader("Content-Type", "application/octet-stream");
        createReadStream(file).pipe(res);
      });
    },
  };
}

// Relative base so the built app can be served from any sub-path.
export default defineConfig({
  base: "./",
  plugins: [react(), serveGamedata()],
});
