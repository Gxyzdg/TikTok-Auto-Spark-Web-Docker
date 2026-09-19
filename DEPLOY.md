# 部署文档（Windows / Linux）

> 本项目为「前端静态页 + 后端 FastAPI」架构。浏览器驱动（Chrome）由**后端所在机器**拉起，
> 因此后端必须部署在装有 Chrome 的机器上，前端（dist）可放在任意静态服务器并反向代理 `/api` 到后端。

```
浏览器 → 前端静态页(dist) ──/api──→ Nginx/反代 ──→ 后端 FastAPI(localhost:9844)
                                                    └─→ Chrome(selenium) ─→ 抖音
```

---

## 一、环境变量总表

### 后端（在启动后端前设置）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `localhost` | 后端监听地址。仅本机访问用 `localhost`；被反代/容器访问用 `0.0.0.0` |
| `PORT` | `9844` | 后端监听端口 |
| `CHROME_DRIVER_PATH` | 空 | chromedriver 绝对路径；**留空则 Selenium Manager 自动下载匹配版本** |
| `SHOW_BROWSER` | 空 | 设为任意非空值则显示浏览器窗口（默认无头 headless） |
| `SCALE_FACTOR` | `1` | 页面缩放系数：`1`（标准横版窗口，清晰可读） |
| `CONFIG_FILE` | 脚本同目录 `config.json`（Docker 为 `/data/config.json`） | 配置文件：仅存管理员密码加盐 PBKDF2 哈希（改密后重启仍生效） |
| `TASKS_FILE` | 脚本同目录 `tasks.json`（Docker 为 `/data/tasks.json`） | 定时任务持久化文件（含已停用任务） |

> 以上均有默认值，一般无需配置；Docker 镜像已全部内置。仅 `VNC_PASSWORD` 需在 compose 里按需修改
> （默认 `123456`，**正式使用前请务必修改**）。

### 前端（构建/开发时）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_PROXY` | `http://localhost:9844` | `npm run dev` 时 `/api` 代理指向的后端地址 |
| `VITE_API_HOST` | `127.0.0.1:9844` | 首页「系统信息」展示用，仅展示不参与请求 |
| `WEB_PORT` | `14320` | Docker 前端对外端口（docker-compose 的端口映射） |
| `NOVNC_PORT` | `14321` | noVNC 对外端口 |

> 实际请求一律走 `/api` 反代，`VITE_API_HOST`/`VITE_FRONTEND_PORT` 只是首页展示值。

---

## 二、Windows 部署

### 1. 环境
- 安装 Chrome（https://www.google.com/chrome/）
- 安装 Python 3.8+（勾选 Add to PATH）

### 2. 后端
```bat
cd 项目目录
pip install -r requirements.txt

:: （可选）手动指定驱动；不设则 Selenium Manager 自动下载
set CHROME_DRIVER_PATH=C:\path\to\chromedriver.exe

:: 启动（默认 localhost:9844）
python 抖音自动续火花-后端.py
```

### 3. 前端
```bat
npm install
npm run build
```
产物在 `dist/`，拷贝到任意静态服务器，并把 `/api` 反向代理到 `http://127.0.0.1:9844`（见第四节 Nginx 示例）。

---

## 三、Linux 部署

### 1. 安装 Chrome 与依赖（以 Ubuntu/Debian 为例）
```bash
# Chrome（若用 chromium 也可，Selenium Manager 能自动识别）
wget -qO /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt install -y /tmp/google-chrome.deb

# 中文字体（headless 截图显示中文必需，昵称等 DOM 文本不受影响）
apt install -y fonts-noto-cjk

# 后端依赖
pip3 install -r requirements.txt
```

### 2. chromedriver（二选一）
```bash
# A. 手动指定（推荐，离线服务器必须）
export CHROME_DRIVER_PATH=/usr/bin/chromedriver   # 或实际路径

# B. 留空：Selenium Manager 在首次 Init 时联网自动下载匹配版本
```

### 3. 启动后端
```bash
export HOST=127.0.0.1   # 被 nginx 反代时用 127.0.0.1 即可；直连/Docker 用 0.0.0.0
export PORT=9844
python3 抖音自动续火花-后端.py
```

### 4. 前端
```bash
npm install && npm run build
# 把 dist/ 放到 web 根目录，/api 反代到后端（见下）
```

### 5. systemd 常驻（可选）
创建 `/etc/systemd/system/tiktok-spark.service`：
```ini
[Unit]
Description=TikTok Auto Spark Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/tiktok-spark
Environment="HOST=127.0.0.1"
Environment="PORT=9844"
Environment="CHROME_DRIVER_PATH=/usr/bin/chromedriver"
ExecStart=/usr/bin/python3 /opt/tiktok-spark/抖音自动续火花-后端.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
systemctl daemon-reload
systemctl enable --now tiktok-spark
journalctl -u tiktok-spark -f   # 看日志
```

---

## 四、Nginx 反代示例（前后端同源）

```nginx
server {
    listen 80;
    server_name your.domain.com;

    root /var/www/tiktok-spark/dist;   # 前端构建产物
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;   # history 路由回退
    }

    # 关键：去掉 /api 前缀再转发到后端（与后端路由一致）
    location /api/ {
        proxy_pass http://127.0.0.1:9844/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;   # 发消息/初始化浏览器较慢，超时给足
    }
}
```

> `proxy_pass .../` 结尾的 `/` 会把 `/api/xxx` 重写为 `/xxx`，与后端路由匹配。
> 若用 Caddy/Apache 等，保持同样的「去 `/api` 前缀 + 同源」逻辑即可。

---

## 五、部署后验证

1. **后端存活**：浏览器访问 `http://127.0.0.1:9844/Home`（无鉴权可返回 `{time: ...}`）。
2. **前端可达**：打开站点首页，能看到登录页。
3. **后台登录**：账户 `admin`，默认密码 `123456`（登录接口已改为 POST + JSON）。
4. **初始化浏览器**：进入首页点「初始化浏览器」，后端日志应出现 Selenium 启动 Chrome。
5. **登录抖音**：扫码 / 验证码 / Base64Cookie 任选其一，成功后状态变为「已登录」。
6. **定时任务**：添加一个任务，确认后端同目录生成 `tasks.json`；重启后端后再点「初始化」，任务自动恢复。

---

## 六、注意事项 / 常见问题

| 现象 | 处理 |
|------|------|
| 初始化报「浏览器驱动与浏览器版本不匹配」 | 更新/重装 chromedriver，或设 `CHROME_DRIVER_PATH` 指向匹配版本 |
| 服务器离线，Selenium Manager 下载失败 | 手动下载 chromedriver 并设 `CHROME_DRIVER_PATH` |
| headless 截图中文变方块 | 安装 `fonts-noto-cjk`（Linux）；Windows 一般自带中文字体 |
| 只能本机访问，外部打不开 | 后端设 `HOST=0.0.0.0`，或通过 Nginx 反代 |
| 验证码/扫码超时 | 检查 Nginx `proxy_read_timeout` 是否过短（建议 ≥60s） |
| 改密码后所有设备被登出 | 正常行为：改密会使全部 token 失效，需重新登录 |
| 同一账号任务重复 | 每任务按「时间_好友」唯一；重启后由 `tasks.json` 恢复，不会重复注册 |

### 已知约束
- **单个浏览器实例**：后端同时只能驱动一个 Chrome（一个抖音账号）。多账号需多实例/多端口。
- **内存态**：登录 token、调度 job 在内存中；`tasks.json` 只持久化定时/停用任务。后端重启后需重新「初始化浏览器」才恢复任务调度。
- 后端与前端分离部署时，后端机器需能访问抖音，且建议固定出口 IP 避免风控。
- 默认密码 `123456` 请尽快在「设置 → 修改密码」中更换。
