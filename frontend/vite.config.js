import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端 API 目标地址：抽为常量并支持环境变量覆盖，避免端口硬编码。
// 与后端 CORS 白名单解耦（只改前端代理配置，不动后端 CORS）。
const apiTarget = process.env.MEMORIA_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': apiTarget
    }
  }
})
