// 全局配置（集中管理，避免散落硬编码）
// 以下展示用信息支持构建期注入：在项目根目录的 .env 中设置 VITE_API_HOST / VITE_FRONTEND_PORT。
// 注意：实际请求走 /api 代理（见 vite.config.js），这里仅用于首页展示，不参与真实网络调用。
export const APP_VERSION = 'v1.2.1'
export const API_HOST = import.meta.env.VITE_API_HOST || '127.0.0.1:9844'
export const FRONTEND_PORT = import.meta.env.VITE_FRONTEND_PORT || '8080'
