import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      // 强制使用 axios 的浏览器 ESM 构建，避免把 Node 端代码（stream/buffer/process）打进浏览器包。
      // 用绝对路径指向 node_modules 内的 ESM 产物，以绕过 package exports 封装（该文件不在 exports 白名单内）。
      { find: /^axios$/, replacement: fileURLToPath(new URL('./node_modules/axios/dist/esm/axios.js', import.meta.url)) }
    ]
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 可用环境变量 VITE_API_PROXY 覆盖后端地址（构建/运行时注入）
        target: process.env.VITE_API_PROXY || 'http://localhost:9844',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})