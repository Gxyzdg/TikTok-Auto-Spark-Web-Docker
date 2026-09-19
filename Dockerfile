# ============================================================
# 抖音火花助手 · v2 精简镜像（前端 + 后端 + Chromium + VNC/noVNC）
#
# 相比 v1（selenium/standalone-chromium 基础镜像）：
#   - 本项目后端直接 webdriver.Chrome() 直连，用不到 Selenium Grid/Java，
#     因此 v2 换成 python:3.12-slim + 自装 chromium，体积约减半
#   - 功能不变：前端 / 后端 / VNC / noVNC / nginx / 任务持久化
#
#   构建: docker build -t gxyzdg/tiktok-spark-auto-web-for-docker:latest .
#   运行: docker compose up -d
#   VNC : 连接 <宿主机IP>:5900，或浏览器访问 noVNC :6080
# ============================================================

# ---------- 阶段一：构建前端 ----------
FROM node:22-alpine AS builder
# 版本号可构建期注入：带 VNC 版本构建为 v1.5.0，无 VNC 版本构建为 v1.5.1
ARG APP_VERSION=v1.5.0
ENV VITE_APP_VERSION=${APP_VERSION}
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --registry=https://registry.npmmirror.com   # 严格按 lockfile + 国内镜像
COPY . .
RUN npm run build
# 产物在 /build/dist

# ---------- 阶段二：运行环境（精简基础镜像） ----------
FROM python:3.12-slim-bookworm

USER root

# 运行期环境变量：全部内置默认值，用户无需配置；仅 VNC_PASSWORD 由 docker-compose 显式传入
ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=9844 \
    DISPLAY=:99 \
    CHROME_DRIVER_PATH=/usr/bin/chromedriver \
    TASKS_FILE=/data/tasks.json \
    CONFIG_FILE=/data/config.json \
    SHOW_BROWSER=1 \
    TZ=Asia/Shanghai \
    SCALE_FACTOR=1 \
    VNC_ENABLED=1

# 是否安装 VNC 组件：1 = 带 VNC（默认，:1.5.0）；0 = 无 VNC 精简版（:1.5.1）
ARG INSTALL_VNC=1
# 容器默认是否启用 VNC（可在 docker-compose 里用 VNC_ENABLED 覆盖）
ARG VNC_ENABLED_DEFAULT=1
ENV VNC_ENABLED=${VNC_ENABLED_DEFAULT}

# Chromium + 驱动 + 中文字体（wqy-microhei，比 noto-cjk 小 ~86MB）
# + Xvfb + openbox 窗口管理器（让窗口可拖动）+ nginx + 工具
# VNC 组件（x11vnc/novnc/websockify）仅在 INSTALL_VNC=1 时安装
# 同一层内完成清理，避免删除的内容残留在上层导致镜像膨胀
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-wqy-microhei \
        xvfb \
        xdotool \
        openbox \
        nginx \
        curl \
    && if [ "$INSTALL_VNC" = "1" ]; then \
         apt-get install -y --no-install-recommends x11vnc novnc websockify ; \
       fi \
    && rm -f /etc/nginx/sites-enabled/default \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/* /var/cache/* \
    && rm -f /usr/bin/xdg-open /usr/bin/xdg-settings

# 抑制"外部协议"模态弹窗（抖音页面会尝试 snssdk1128:// / douyin:// 等自定义协议拉起 App，
# Chromium 会弹"是否允许打开 xdg-open"的**模态框**，该弹窗会阻断页面输入 → 远程操作失效）。
# AutoLaunchProtocolsFromOrigins：匹配的来源+协议直接静默处理，不再弹框；
# 同时 xdg-open 已删除，即使触发也不会有任何动作。
RUN mkdir -p /etc/chromium/policies/managed && cat > /etc/chromium/policies/managed/spark-external-protocol.json <<'EOF'
{
  "AutoLaunchProtocolsFromOrigins": [
    { "protocol": "snssdk1128", "allowed_origins": ["*"] },
    { "protocol": "snssdk1233", "allowed_origins": ["*"] },
    { "protocol": "douyin", "allowed_origins": ["*"] },
    { "protocol": "aweme", "allowed_origins": ["*"] },
    { "protocol": "webcast", "allowed_origins": ["*"] },
    { "protocol": "sslocal", "allowed_origins": ["*"] },
    { "protocol": "bytedance", "allowed_origins": ["*"] },
    { "protocol": "toutiao", "allowed_origins": ["*"] },
    { "protocol": "ixigua", "allowed_origins": ["*"] },
    { "protocol": "newsarticle", "allowed_origins": ["*"] }
  ],
  "ExternalProtocolDialogShowAlwaysOpenCheckbox": false
}
EOF

# 后端依赖
WORKDIR /app
COPY requirements.txt ./
# 使用国内镜像源：直连 PyPI 在国内会非常慢（实测十几分钟都装不完）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY 抖音自动续火花-后端.py ./抖音自动续火花-后端.py

# 前端产物 + nginx 配置 + 启动脚本 + noVNC 首页
COPY --from=builder /build/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/novnc-index.html /usr/share/novnc/index.html
RUN chmod +x /entrypoint.sh && mkdir -p /data

# 数据卷：tasks.json / config.json 持久化（后端重启自动恢复）
VOLUME ["/data"]

EXPOSE 80 9844 5900 6080

# 健康检查：前端静态页 + 后端 /healthz（不再依赖 /docs，生产已默认关闭 Swagger）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:80/ > /dev/null 2>&1 && curl -fsS http://127.0.0.1:9844/healthz > /dev/null 2>&1 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
