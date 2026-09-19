#!/bin/bash
set -e

# 兜底默认值（docker-compose 已设，这里防止直接 docker run 时缺失）
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-9844}"
export DISPLAY="${DISPLAY:-:99}"
export CHROME_DRIVER_PATH="${CHROME_DRIVER_PATH:-/usr/bin/chromedriver}"
VNC_PASSWORD="${VNC_PASSWORD:-123456}"
# VNC_ENABLED：是否启动 x11vnc/noVNC（默认 1 开启）。
# 登录向导（/wizard）已内置 CDP 画面串流，可设为 0 彻底关闭 VNC 及其端口。
VNC_ENABLED="${VNC_ENABLED:-1}"
# 对外端口（与 docker-compose 的端口映射保持一致）：仅用于前端界面展示，
# 让首页「前端端口 / API 地址 / noVNC 端口」跟随自定义映射自动变化。
NOVNC_PORT="${NOVNC_PORT:-6080}"
# 注意：这里**不给默认值**——没映射后端端口时保持为空，前端会隐藏「API 地址」一行
API_PORT="${API_PORT:-}"

# 生成运行时配置（前端 index.html 会先加载它），自定义端口后无需重新构建前端
cat > /usr/share/nginx/html/runtime-config.js <<EOF
// 由容器 entrypoint 自动生成，请勿手改
window.__SPARK_RUNTIME__ = {
  novncPort: "${NOVNC_PORT}",
  apiPort: "${API_PORT}",
  vncEnabled: "${VNC_ENABLED}"
};
EOF
chmod 644 /usr/share/nginx/html/runtime-config.js   # nginx 以 www-data 运行，必须可读
echo "[entrypoint] 已写入运行时配置：noVNC 端口 ${NOVNC_PORT} / 后端端口 ${API_PORT}"

# 容器重启时 /tmp 会保留上一次运行的残留文件：
#   - /tmp/.X99-lock 会让新的 Xvfb 直接报 "Server is already active for display 99" 后退出，
#     进而触发 wait -n 退出 → 容器陷入无限重启（必须清理，否则 docker restart 必崩）
DISPLAY_NUM="${DISPLAY#:}"
echo "[entrypoint] 清理上一次运行的 X 残留（锁文件 / socket / 日志）..."
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true
rm -f /tmp/xvfb.log /tmp/openbox.log /tmp/x11vnc.log /tmp/websockify.log 2>/dev/null || true

echo "[entrypoint] 启动虚拟显示器 Xvfb (${DISPLAY}) ..."
# 屏幕尺寸与浏览器 window-size 一致；如需更小的 VNC 视图可自行调整
Xvfb "$DISPLAY" -screen 0 1400x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 1

echo "[entrypoint] 启动窗口管理器 openbox（让窗口可拖动/带标题栏）..."
DISPLAY="$DISPLAY" openbox --sm-disable >/tmp/openbox.log 2>&1 &
OPENBOX_PID=$!
sleep 1

if [ "$VNC_ENABLED" = "0" ] || [ "$VNC_ENABLED" = "false" ] || [ "$VNC_ENABLED" = "no" ]; then
    echo "[entrypoint] VNC_ENABLED=${VNC_ENABLED} → 跳过 x11vnc / noVNC（改用登录向导的内置画面串流）"
    VNC_PID=""
    NOVNC_PID=""
elif ! command -v x11vnc >/dev/null 2>&1 || ! command -v websockify >/dev/null 2>&1; then
    # 无 VNC 精简版镜像（:1.5.1）不包含 VNC 组件，即使 VNC_ENABLED=1 也要优雅跳过
    echo "[entrypoint] 当前镜像未包含 VNC 组件（无 VNC 版本），跳过 x11vnc / noVNC"
    VNC_PID=""
    NOVNC_PID=""
else
    echo "[entrypoint] 启动 VNC（端口 5900，密码: ${VNC_PASSWORD}）..."
    x11vnc -display "$DISPLAY" -forever -shared -passwd "$VNC_PASSWORD" -rfbport 5900 -noxdamage >/tmp/x11vnc.log 2>&1 &
    VNC_PID=$!

    echo "[entrypoint] 启动 noVNC 网页版 VNC（端口 6080 -> 5900，浏览器访问 /vnc.html）..."
    websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >/tmp/websockify.log 2>&1 &
    NOVNC_PID=$!
fi

echo "[entrypoint] 启动后端 uvicorn (${HOST}:${PORT}) ..."
python3 /app/抖音自动续火花-后端.py &
BACKEND_PID=$!

echo "[entrypoint] 启动 nginx ..."
nginx -g 'daemon off;' &
NGINX_PID=$!

# 等待 nginx 就绪（最多约 15s）
for _ in $(seq 1 15); do
    if curl -fsS http://127.0.0.1/ >/dev/null 2>&1; then break; fi
    sleep 1
done

cleanup() {
    echo "[entrypoint] 收到退出信号，清理进程..."
    kill "$BACKEND_PID" "$NGINX_PID" ${VNC_PID:+"$VNC_PID"} ${NOVNC_PID:+"$NOVNC_PID"} "$OPENBOX_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup TERM INT

# 任一核心进程退出（崩溃）则整个容器退出，交给 Docker restart 策略自动拉起。
# openbox（窗口管理器）不属核心进程：它退出不影响应用运行，若加入 wait 会因它退出导致容器闪退。
# VNC 关闭时对应 PID 为空，wait -n 会自动忽略。
wait -n "$BACKEND_PID" "$NGINX_PID" ${VNC_PID:+"$VNC_PID"} ${NOVNC_PID:+"$NOVNC_PID"} "$XVFB_PID"
exit $?
