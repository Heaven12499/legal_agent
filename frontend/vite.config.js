import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    // 开发时前端 5173 请求 /api 直接代理到后端 8000，免 CORS
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
