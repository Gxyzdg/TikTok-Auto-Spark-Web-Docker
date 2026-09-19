// 全局配置（集中管理，避免散落硬编码）
//
// 端口一律在**运行时**决定，容器自定义端口映射后无需重新构建前端：
//   1) 前端端口：直接取浏览器地址栏的端口（反代场景下也是最终对外端口）；
//   2) noVNC / 后端端口：由容器 entrypoint 生成 /runtime-config.js 注入
//      （对应环境变量 NOVNC_PORT / API_PORT，与 docker-compose 的端口映射保持一致）。
// 仍兼容构建期注入（.env 里的 VITE_* 变量）作为兜底。
// 注意：真实请求走 /api 代理（见 vite.config.js），这里的地址仅用于界面展示。

const runtime = (typeof window !== 'undefined' && window.__SPARK_RUNTIME__) || {}

/** 当前访问地址的端口（80/443 时浏览器返回空串，这里换回标准端口） */
const locationPort = (() => {
  if (typeof window === 'undefined' || !window.location) return ''
  const { protocol, port } = window.location
  if (port) return port
  return protocol === 'https:' ? '443' : '80'
})()

export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'v1.5.0'

/**
 * 后端直连地址（首页「API 地址」展示用）。
 * 没映射后端端口时（runtime.apiPort 为空）返回空串 → 首页不显示该行，避免展示一个访问不到的地址。
 */
export const API_HOST =
  runtime.apiHost || import.meta.env.VITE_API_HOST ||
  (runtime.apiPort ? `${location.hostname}:${runtime.apiPort}` : '')

/** VNC 是否启用（无 VNC 镜像内置为 0） */
export const VNC_ENABLED = String(runtime.vncEnabled ?? '1') !== '0'

/** 前端访问端口（首页「前端端口」展示用）——始终跟随实际访问地址 */
export const FRONTEND_PORT = locationPort || import.meta.env.VITE_FRONTEND_PORT || '8080'

/** noVNC 对外端口（容器里用 NOVNC_PORT 环境变量指定） */
export const NOVNC_PORT = String(runtime.novncPort || import.meta.env.VITE_NOVNC_PORT || '6080')

/** noVNC 网页版地址（跟随当前访问的协议与主机） */
export const NOVNC_URL =
  typeof window === 'undefined'
    ? `http://127.0.0.1:${NOVNC_PORT}/`
    : `${window.location.protocol}//${window.location.hostname}:${NOVNC_PORT}/`
