/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const target = process.env.OWL_API ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": target, "^/r/[^/]+/api/": target } },
  preview: { port: 4173, proxy: { "/api": target, "^/r/[^/]+/api/": target } },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
