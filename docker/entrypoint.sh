#!/bin/bash
set -e

# 兜底默认值（docker-compose 已设，这里防止直接 docker run 时缺失）
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-9844}"
export DISPLAY="${DISPLAY:-:99}"
export CHROME_DRIVER_PATH="${CHROME_DRIVER_PATH:-/usr/bin/chromedriver}"
# ===== 管理员密码（Web 后台与 noVNC 共用同一份）=====
#   - PASSWORD 环境变量：设置且符合强度要求时直接沿用（不重置、不强制改密），
#     已存在配置文件时等价于重置密码（Web 与 noVNC 同步）；
#   - 未设置：沿用 /data/.password 里保存的口令（重建容器 / 升级镜像后不变）；
#   - 都没有：生成 12 位随机一次性口令并打印到 docker logs，登录 Web 后强制修改。
#   - Web 端改密后，后端会重写同一文件并重启 x11vnc，两边密码始终一致。
#   - 兼容旧变量名 VNC_PASSWORD / ADMIN_PASSWORD 与旧文件 /data/.vnc_password。
PASSWORD_FILE="${PASSWORD_FILE:-/data/.password}"
LEGACY_PASSWORD_FILE="${LEGACY_PASSWORD_FILE:-/data/.vnc_password}"
if [ ! -s "$PASSWORD_FILE" ] && [ -s "$LEGACY_PASSWORD_FILE" ]; then
    if mv -f "$LEGACY_PASSWORD_FILE" "$PASSWORD_FILE" 2>/dev/null; then
        echo "[entrypoint] 已把旧口令文件 .vnc_password 迁移为 .password"
    else
        cp -f "$LEGACY_PASSWORD_FILE" "$PASSWORD_FILE" 2>/dev/null || true
    fi
    chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
fi

_custom_pwd="${PASSWORD:-${ADMIN_PASSWORD:-${VNC_PASSWORD:-}}}"
_weak_pwd=0
case "$_custom_pwd" in
    12345678|123456789|1234567890|password|password1|admin123|88888888) _weak_pwd=1 ;;
esac
if [ -n "$_custom_pwd" ] && { [ ${#_custom_pwd} -lt 8 ] || [ ${#_custom_pwd} -gt 64 ]; }; then
    echo "[entrypoint] ⚠️ 环境变量 PASSWORD 长度需在 8-64 位之间，已忽略；改用已保存/随机生成的口令"
    unset PASSWORD
elif [ -n "$_custom_pwd" ] && [ "$_weak_pwd" = "1" ]; then
    echo "[entrypoint] ⚠️ 环境变量 PASSWORD 过于常见（弱口令），已忽略；改用已保存/随机生成的口令"
    unset PASSWORD
elif [ -n "$_custom_pwd" ]; then
    export PASSWORD="$_custom_pwd"
    mkdir -p "$(dirname "$PASSWORD_FILE")"
    printf '%s' "$_custom_pwd" > "$PASSWORD_FILE"
    chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
    echo "[entrypoint] 已采用环境变量 PASSWORD 作为管理员密码（Web 后台与 noVNC 通用）"
fi

INITIAL_ADMIN_PASSWORD=""
if [ -n "${PASSWORD:-}" ]; then
    INITIAL_ADMIN_PASSWORD="$PASSWORD"
elif [ -s "$PASSWORD_FILE" ]; then
    INITIAL_ADMIN_PASSWORD="$(cat "$PASSWORD_FILE")"
    echo "[entrypoint] 已读取已保存的登录密码（Web 后台与 noVNC 通用）"
else
    INITIAL_ADMIN_PASSWORD="$(head -c 64 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 12)"
    mkdir -p "$(dirname "$PASSWORD_FILE")"
    printf '%s' "$INITIAL_ADMIN_PASSWORD" > "$PASSWORD_FILE"
    chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
    echo "=============================================================="
    echo "[entrypoint] 🔐 首次启动：已生成一次性管理员密码"
    echo "[entrypoint]    用户名：${ADMIN_USERNAME:-admin}"
    echo "[entrypoint]    密  码：${INITIAL_ADMIN_PASSWORD}"
    echo "[entrypoint]    Web 后台与 noVNC 使用同一密码，登录后必须修改。"
    echo "=============================================================="
fi
export INITIAL_ADMIN_PASSWORD
export PASSWORD_FILE
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
# VNC_ENABLED：是否启动 x11vnc/noVNC（默认 1 开启）。
# 登录向导（/wizard）已内置 CDP 画面串流，可设为 0 彻底关闭 VNC 及其端口。
VNC_ENABLED="${VNC_ENABLED:-1}"
# 对外端口（与 docker-compose 的端口映射保持一致）：仅用于前端界面展示，
# 让首页「前端端口 / API 地址 / noVNC 端口」跟随自定义映射自动变化。
NOVNC_PORT="${NOVNC_PORT:-6080}"
if [ "$INITIAL_ADMIN_PASSWORD" = "123456" ] || [ "$INITIAL_ADMIN_PASSWORD" = "admin" ]; then
    echo "[entrypoint] ⚠️ 安全提醒：当前密码是弱口令，noVNC 能直接看到并操作容器里已登录的抖音。"
    echo "[entrypoint] ⚠️ 建议删掉 compose 里的 PASSWORD，改为自动生成随机密码（PASSWORD 留空）。"
fi
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
# 受监管启动：openbox 退出后自动重启。
# 它一旦挂掉，xdotool windowactivate 会失效 → 抖音的外部协议模态弹窗无法被自动关闭 →
# 页面输入被吞（v1.5.0 花大力气修的问题会复现），所以必须保证它一直活着。
(
  while :; do
    DISPLAY="$DISPLAY" openbox --sm-disable >>/tmp/openbox.log 2>&1
    echo "[entrypoint] openbox 退出，1 秒后重启..." >>/tmp/openbox.log
    sleep 1
  done
) &
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
    echo "[entrypoint] 启动 VNC（端口 5900，密码已设置）..."
    # VNC 不是核心进程（挂在 wait -n 里会让 VNC 一崩就整容器重启循环），
    # 但它的日志必须进 docker logs，否则画面异常时无从排查。
    # 守护循环：Web 后台改密后后端会 pkill x11vnc，这里自动用新口令重启，保证两边密码一致。
    (
      while :; do
        x11vnc -display "$DISPLAY" -forever -shared -passwdfile "$PASSWORD_FILE" -rfbport 5900 -noxdamage 2>&1 \
            | sed -u 's/^/[x11vnc] /'
        echo "[entrypoint] x11vnc 已退出，1 秒后重启（改密后重启以加载新口令）"
        sleep 1
      done
    ) &
    VNC_PID=$!

    echo "[entrypoint] 启动 noVNC 网页版 VNC（端口 6080 -> 5900，浏览器访问 /vnc.html）..."
    websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 2>&1 \
        | sed -u 's/^/[websockify] /' &
    NOVNC_PID=$!
fi

echo "[entrypoint] 启动后端 uvicorn (${HOST}:${PORT}) ..."
python3 -u /app/抖音自动续火花-后端.py &   # -u 无缓冲：否则应用日志会被缓冲，很久才出现在 docker logs 里，无法及时排障
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
    pkill -x x11vnc 2>/dev/null || true
    pkill -f "websockify --web" 2>/dev/null || true
}
trap cleanup TERM INT

# 任一核心进程退出（崩溃）则整个容器退出，交给 Docker restart 策略自动拉起。
# 核心进程只有：后端、nginx、Xvfb。openbox 与 VNC 不参与——它们挂掉不该让整个
# 容器闪退（否则一次 VNC 启动失败 = 无限重启循环，连定时任务都会一起停摆）。
wait -n "$BACKEND_PID" "$NGINX_PID" "$XVFB_PID"
exit $?
