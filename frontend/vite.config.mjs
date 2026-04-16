import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/trips": "http://127.0.0.1:8000",
      "/bookings": "http://127.0.0.1:8000",
      "/groups": "http://127.0.0.1:8000",
      "/trackers": "http://127.0.0.1:8000"
    }
  }
});
