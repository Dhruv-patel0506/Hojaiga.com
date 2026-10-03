import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The visual_world dev server is a pure, read-only observer.
// It never opens outbound connections other than the Hojaiga CNS
// visual-adapter WebSocket (ws://127.0.0.1:8080), which is configured
// via VITE_HOJAIGA_WS_URL (see .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
