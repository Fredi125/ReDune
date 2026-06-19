import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built app can be served from any sub-path.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
