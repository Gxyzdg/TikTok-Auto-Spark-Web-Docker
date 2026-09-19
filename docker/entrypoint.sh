#!/bin/bash
set -e

# 兜底默认值（docker-compose 已设，这里防止直接 docker run 时缺失）
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-9844}"
export DISPLAY="${DISPLAY:-:99}"
export CHROME_DRIVER_PATH="${CHROME_DRIVER_PATH:-/usr/bin/chromedriver}"
VNC_PASSWORD="${VNC_PASSWORD:-123456}"

echo "[entrypoint] 启动虚拟显示器 Xvfb (${DISPLAY}) ..."
# 屏幕尺寸与浏览器 window-size 一致；如需更小的 VNC 视图可自行调整
Xvfb "$DISPLAY" -screen 0 1400x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 1

echo "[entrypoint] 启动窗口管理器 openbox（让窗口可拖动/带标题栏）..."
DISPLAY="$DISPLAY" openbox --sm-disable >/tmp/openbox.log 2>&1 &
OPENBOX_PID=$!
sleep 1

echo "[entrypoint] 启动 VNC（端口 5900，密码: ${VNC_PASSWORD}）..."
x11vnc -display "$DISPLAY" -forever -shared -passwd "$VNC_PASSWORD" -rfbport 5900 -noxdamage >/tmp/x11vnc.log 2>&1 &
VNC_PID=$!

echo "[entrypoint] 启动 noVNC 网页版 VNC（端口 6080 -> 5900，浏览器访问 /vnc.html）..."
websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >/tmp/websockify.log 2>&1 &
NOVNC_PID=$!

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
    kill "$BACKEND_PID" "$NGINX_PID" "$VNC_PID" "$NOVNC_PID" "$OPENBOX_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup TERM INT

# 任一核心进程退出（崩溃）则整个容器退出，交给 Docker restart 策略自动拉起。
# openbox（窗口管理器）不属核心进程：它退出不影响应用运行，若加入 wait 会因它退出导致容器闪退。
wait -n "$BACKEND_PID" "$NGINX_PID" "$VNC_PID" "$NOVNC_PID" "$XVFB_PID"
exit $?
