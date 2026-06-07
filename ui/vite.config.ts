import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// Build to ./dist; FastAPI serves dist/index.html and mounts dist/assets at /assets.
// During `npm run dev`, proxy API + websocket calls to the Python server on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
