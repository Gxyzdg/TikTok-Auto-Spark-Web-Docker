// 运行时配置（默认值，供本地开发 / 静态托管使用）
// 容器启动时 entrypoint 会用实际端口覆盖本文件（见 docker/entrypoint.sh），
// 因此自定义端口映射后不需要重新构建前端。
window.__SPARK_RUNTIME__ = {
  novncPort: '14321',  // noVNC 对外端口（容器里用 NOVNC_PORT 环境变量指定）
  apiPort: '',         // 后端对外端口；留空表示未对外映射（首页隐藏「API 地址」）
  vncEnabled: '1'
}
