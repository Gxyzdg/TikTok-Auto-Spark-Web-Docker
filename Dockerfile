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
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm install --no-audit --no-fund
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
    SCALE_FACTOR=1

# Chromium + 驱动 + 中文字体（wqy-microhei，比 noto-cjk 小 ~86MB）
# + Xvfb/VNC/noVNC + openbox 窗口管理器（让窗口可拖动）+ nginx + 工具
# 同一层内完成清理，避免删除的内容残留在上层导致镜像膨胀
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-wqy-microhei \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        xdotool \
        openbox \
        nginx \
        curl \
    && rm -f /etc/nginx/sites-enabled/default \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/* /var/cache/* \
    && rm -f /usr/bin/xdg-open /usr/bin/xdg-settings

# 后端依赖
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:80/ > /dev/null 2>&1 && curl -fsS http://127.0.0.1:9844/docs > /dev/null 2>&1 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
