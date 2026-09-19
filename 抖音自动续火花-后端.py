import re
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.by import By
import schedule, requests
import time, uvicorn, asyncio, urllib.request
from datetime import datetime, timezone
import json, base64, os, platform, subprocess
from fastapi import FastAPI, Header, Request, Body, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import threading, hashlib, secrets

try:  # CDP 画面串流用（uvicorn[standard] 已包含，这里做防御性导入）
    import websockets
except Exception:  # pragma: no cover
    websockets = None

# 常用环境变量（均有默认值，一般无需配置；Docker 镜像已内置）：
#   HOST / PORT          监听地址与端口（默认 localhost:9844）
#   CHROME_DRIVER_PATH   chromedriver 绝对路径（留空则用 Selenium Manager 自动匹配下载）
#   SHOW_BROWSER         设为任意非空值则显示浏览器窗口（默认无头模式）
#   SCALE_FACTOR         页面缩放系数。默认 1（正常大小，VNC 查看清晰）；新版 Chromium 下 0.25 会导致窗口异常，不建议使用
#   CONFIG_FILE / TASKS_FILE  管理员密码与定时任务的持久化文件路径（Docker 内置 /data/ 下）
CHROME_DRIVER_PATH = os.environ.get('CHROME_DRIVER_PATH', '')
SHOW_BROWSER = os.environ.get('SHOW_BROWSER', '') != ''
SCALE_FACTOR = os.environ.get('SCALE_FACTOR', '1')

service = Service(executable_path=CHROME_DRIVER_PATH) if CHROME_DRIVER_PATH else None
off_ui = not SHOW_BROWSER


def _build_user_agent() -> str:
    """按当前操作系统生成与浏览器平台指纹一致的 UA。"""
    chrome_ver = "110.0.5481.177"
    sys_name = platform.system()
    if sys_name == 'Windows':
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"
    if sys_name == 'Darwin':
        return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"
    return f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"


def _clear_profile_locks(profile_dir: str):
    """清理 Chromium 单例锁残留（Singleton*）。

    容器被 docker 强制重建/浏览器被 kill -9 时，user-data-dir 里会残留
    SingletonLock（指向已销毁容器的主机名）与已失效的 SingletonSocket，
    导致新实例启动即退出，chromedriver 报 "DevToolsActivePort file doesn't exist"。
    调用前请确保没有本项目启动的 Chromium 正在使用该资料目录。
    """
    removed = []
    for name in ('SingletonLock', 'SingletonSocket', 'SingletonCookie'):
        path = os.path.join(profile_dir, name)
        try:
            if os.path.islink(path) or os.path.exists(path):
                os.remove(path)
                removed.append(name)
        except Exception as e:
            print(f'⚠️ 清理浏览器配置锁 {name} 失败: {e}')
    if removed:
        log(f'🧹 已清理浏览器资料目录残留锁：{", ".join(removed)}')


def unban_config():
    """构建并返回 ChromeOptions。

    每次调用都新建独立对象（幂等）：即使 /Api/Init 首次失败后重试，也不会在同一
    options 上叠加重复参数。平台相关参数（UA）按当前操作系统生成。
    """
    opts = webdriver.ChromeOptions()
    if off_ui:
        opts.add_argument("--headless")  # 启用无头模式
    opts.add_experimental_option('excludeSwitches', ['enable-logging'])
    opts.add_argument('log-level=3')
    opts.add_argument("user-agent=" + _build_user_agent())
    opts.add_experimental_option('excludeSwitches', ['enable-automation', 'useAutomationExtension'])
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-infobars')
    opts.add_argument('--disable-notifications')
    opts.add_argument('--disable-popup-blocking')
    opts.add_argument('--disable-web-security')
    opts.add_argument('--ignore-certificate-errors')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')  # 容器/无头环境 /dev/shm 过小时必需
    # 避免首次运行/默认浏览器/xdg 弹窗（容器无桌面环境时这些会弹"是否允许 xdg"确认框）
    opts.add_argument('--no-first-run')
    opts.add_argument('--no-default-browser-check')
    opts.add_argument('--disable-session-crashed-bubble')
    # 抑制"是否允许 xdg-open"外部协议确认弹窗（容器无桌面环境时每次启动都会弹）
    opts.add_argument('--disable-features=ExternalProtocolDialog,Translate,MediaRouter,OptimizationHints,OptimizationGuideModelDownloading')
    # 性能：Xvfb 下窗口不会获得焦点，Chromium 默认会节流后台定时器/渲染，导致自动化变慢
    opts.add_argument('--disable-background-timer-throttling')
    opts.add_argument('--disable-backgrounding-occluded-windows')
    opts.add_argument('--disable-renderer-backgrounding')
    opts.add_argument('--disable-ipc-flooding-protection')
    opts.add_argument('--disable-hang-monitor')
    opts.add_argument('--disable-component-update')
    opts.add_argument('--disable-default-apps')
    opts.add_argument('--no-pings')
    # 保存登录数据（Cookie）：开启时使用持久化 user-data-dir，浏览器重启后仍保持抖音登录
    if _config.get('save_session'):
        try:
            profile_dir = os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE)), 'chrome-profile')
            os.makedirs(profile_dir, exist_ok=True)
            _clear_profile_locks(profile_dir)
            opts.add_argument(f'--user-data-dir={profile_dir}')
            log(f'💾 已启用登录数据保存，浏览器资料目录：{profile_dir}')
        except Exception as e:
            log(f'⚠️ 启用登录数据保存失败（将使用临时目录）：{e}')
    opts.add_argument('--window-size=1280,720')  # 标准横版窗口，页面全部按钮可用
    opts.add_argument(f"--force-device-scale-factor={SCALE_FACTOR}")
    return opts


_quote_cache = {'text': None, 'ts': 0.0}
_QUOTE_TTL = 6 * 3600  # 名言缓存 6 小时，避免恢复多个任务/多次添加时反复请求外部 API


def AiqingGongyu_text():
    """获取每日名言；结果缓存 _QUOTE_TTL 秒，失败不缓存（下次重试）。"""
    now = time.time()
    if _quote_cache['text'] and (now - _quote_cache['ts']) < _QUOTE_TTL:
        return _quote_cache['text']
    text = '暂无今日名言'
    try:
        req = requests.get('https://v2.xxapi.cn/api/aiqinggongyu', timeout=5)
        if req.status_code == 200:
            json_data = req.json()
            text = json_data.get('data') or '暂无今日名言'
    except Exception:
        return '暂无今日名言'
    _quote_cache['text'] = text
    _quote_cache['ts'] = now
    return text


def format_time(time_str: str) -> str:
    """
    将时间字符串格式化为 HH:MM 格式
    例如: "9:23" -> "09:23", "9:5" -> "09:05", "09:23" -> "09:23"
    """
    if not time_str:
        return '22:00'

    # 统一替换中文冒号
    time_str = time_str.replace('：', ':').strip()

    try:
        # 分割小时和分钟
        parts = time_str.split(':')
        if len(parts) != 2:
            print(f'⚠️ 时间格式错误，使用默认时间 22:00')
            return '22:00'

        hour = int(parts[0])
        minute = int(parts[1])

        # 验证范围
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            print(f'⚠️ 时间范围错误，使用默认时间 22:00')
            return '22:00'

        # 格式化为两位数字
        return f"{hour:02d}:{minute:02d}"

    except ValueError:
        print(f'⚠️ 时间解析错误，使用默认时间 22:00')
        return '22:00'


class TrueString:
    def __init__(self, is_bool, string):
        self.is_bool = is_bool
        self.string = string


class UserFriendsInfo:
    def __init__(self, username, avatar, fire):
        self.username = username
        self.avatar = avatar
        self.fire = fire


class Douyin:
    FRIENDS_CACHE_TTL = 30.0  # 好友列表缓存有效期（秒），批量添加时避免每个好友都全量爬取

    def __init__(self, driver):
        self.driver = driver  # 将 driver 作为实例属性
        self.friends_xpath_list = {}
        self._friends_cache_time = 0.0

    def Updara_FrinderList(self):
        with driver_lock:
            wrapper_xpath = '//div[@class="conversationConversationListwrapper"]'
            friends_xpath = wrapper_xpath + '/div/div/div'
            # 会话列表是虚拟滚动的：窗口较小时只渲染可视区的好友。
            # 循环滚动列表到底部触发懒加载，确保抓取全部好友（数量统计/定时任务依赖完整列表）。
            try:
                wrapper_el = driver.find_element(By.XPATH, wrapper_xpath)
            except Exception:
                wrapper_el = None
            prev_count = -1
            for _ in range(60):
                items = driver.find_elements(By.XPATH, friends_xpath)
                if wrapper_el is not None:
                    try:
                        # 滚动 wrapper 内所有可滚动容器到底部，触发虚拟列表懒加载更多会话
                        driver.execute_script(
                            'var roots=[arguments[0]].concat(Array.prototype.slice.call(arguments[0].querySelectorAll("*")));'
                            'for(var i=0;i<roots.length;i++){var e=roots[i];'
                            'if(e.scrollHeight>e.clientHeight+2){e.scrollTop=e.scrollHeight;}}',
                            wrapper_el,
                        )
                    except Exception:
                        pass
                time.sleep(0.4)
                items2 = driver.find_elements(By.XPATH, friends_xpath)
                if len(items2) == len(items) and len(items) == prev_count:
                    break
                prev_count = len(items)
            msg_main_list = driver.find_elements(By.XPATH, friends_xpath)
            temp_list = []
            for msg_len in range(1, len(msg_main_list) + 1):
                # 单个条目解析失败仅跳过该条，不影响整体列表（DOM 结构微变/缺字段时更稳）
                try:
                    new_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[2]/div[1]/div[1]'
                    avatar_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[1]/div/span/img'
                    avatar_xpath2 = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div/div/img'
                    fire_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[2]/div[1]/div[2]/div[1]/div/div'
                    friends_get = driver.find_element(By.XPATH, value=new_xpath)
                    friends_text = friends_get.text
                    if not friends_text:
                        continue  # 空名字条目跳过
                    try:
                        avatar_get = driver.find_element(By.XPATH, value=avatar_xpath)
                        avatar = avatar_get.get_attribute('src')
                    except:
                        try:
                            avatar_get = driver.find_element(By.XPATH, value=avatar_xpath2)
                            avatar = avatar_get.get_attribute('src')
                        except:
                            avatar = ''
                    self.friends_xpath_list[friends_text] = new_xpath
                    try:
                        fire_count = driver.find_element(By.XPATH, value=fire_xpath).text.strip()
                    except:
                        fire_count = ''
                    temp_list.append(UserFriendsInfo(friends_text, avatar, fire_count))
                except Exception:
                    continue
            self._friends_cache_time = time.time()
            return temp_list

    def Send_Frinder(self, name: str, text: str):
        with driver_lock:
            try:
                count = self.Updara_FrinderList()
            except Exception as e:
                return TrueString(False, e)
            if count == 0:
                print("⚠️ 更新好友列表失败!")
                return TrueString(False, '未获取到好友列表')
            try:
                for index, value in self.friends_xpath_list.items():
                    if index == name:
                        friend_id = driver.find_element(By.XPATH, value=value)
                        friend_id.click()
                        time.sleep(1.5)
                        seng = driver.find_element(By.XPATH,
                                                   value='//div[@class="messageEditorimChatEditorContainer"]/div/div')
                        seng.send_keys(text)
                        seng.send_keys(Keys.ENTER)
                        return TrueString(True, None)
            except Exception as e:
                return TrueString(False, e)
            # 好友列表非空但循环未匹配到该好友
            return TrueString(False, '未找到该好友')

    def Find_Friends(self, name: str):
        with driver_lock:
            # 优先使用缓存校验好友是否存在，避免批量添加任务时每个好友都全量爬取一遍好友列表
            try:
                now = time.time()
                if not self.friends_xpath_list or (now - self._friends_cache_time) > self.FRIENDS_CACHE_TTL:
                    count = self.Updara_FrinderList()
                    if not count:
                        return TrueString(False, '未初始化好友')
                return TrueString(name in self.friends_xpath_list, None)
            except Exception as e:
                # 爬取异常转成业务错误返回，避免 500 透传到调用方
                return TrueString(False, f'好友列表获取失败: {e}')

    def LoginInit(self):
        try:
            dle_user = driver.find_element(By.XPATH,
                                           value='//*[@id="douyin_login_comp_flat_panel"]/div/div[2]/div/div[4]/p')
            dle_user.click()
        except:
            pass


init = False
Login_is_bool = False
driver_lock = threading.RLock()  # 串行化 driver 操作，避免调度线程与请求线程并发冲突
init_lock = threading.RLock()    # 保护 Init 的 check-then-act，避免并发请求初始化出多个 driver
tasks_lock = threading.RLock()   # 保护 scheduled_tasks / paused_tasks 的并发读写
tokens_lock = threading.Lock()   # 保护 _valid_tokens 的并发访问
app = FastAPI()

# CORS 配置：仅允许本地来源（前端与后端同源反代部署时实际不触发跨域）
_cors_origins = [
    'http://localhost:9844', 'http://localhost:5173',
    'http://127.0.0.1:9844', 'http://127.0.0.1:5173',
    'http://localhost', 'http://127.0.0.1',
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= 密码存储（加盐 PBKDF2 + 配置文件持久化） =================
# 哈希格式: pbkdf2_sha256$迭代次数$盐(hex)$哈希(hex)；默认密码仍为 admin/123456
_PBKDF2_ITERATIONS = 100_000
_password_hash = None  # 当前管理员密码哈希（启动时从配置文件加载）


def _hash_password(pwd: str, salt: bytes = None, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """生成加盐 PBKDF2 哈希；每次调用使用新随机盐。"""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'


def _verify_password(pwd: str, stored: str) -> bool:
    """校验密码与存储的加盐哈希是否匹配（恒定时间比较）。"""
    if not pwd or not stored:
        return False
    try:
        algo, iterations, salt_hex, hash_hex = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


# ================= 配置文件持久化（仅存管理员密码哈希） =================
# 默认脚本同目录 config.json；Docker 镜像内置 CONFIG_FILE=/data/config.json（数据卷持久化）
CONFIG_FILE = os.environ.get(
    'CONFIG_FILE',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
)
_config = {}


def _save_config():
    """把当前配置（含密码哈希）写回配置文件。"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 配置持久化失败: {e}')


def _load_config():
    """启动时加载配置；首次运行生成默认密码 admin/123456 的加盐哈希并落盘。"""
    global _password_hash
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            print(f'⚠️ 配置读取失败，将使用默认配置: {e}')
            cfg = {}
    # 持久化字段：password（管理员密码哈希）、save_session（是否保存抖音登录数据，默认关闭）
    password = cfg.get('password')
    save_session = bool(cfg.get('save_session', False))
    _config.clear()
    _config['save_session'] = save_session
    if not password:
        _password_hash = _hash_password('123456')  # 默认密码 admin/123456
        _config['password'] = _password_hash
        _save_config()
        print('✅ 已生成默认管理员密码（admin/123456）加盐哈希并持久化')
    else:
        _config['password'] = password
        _password_hash = password
    print(f'📄 配置文件: {CONFIG_FILE}')


_load_config()

# 登录 token 有效期：固定 7 天
TOKEN_TTL_SECONDS = 7 * 24 * 3600


# Token存储：token -> 过期时间戳
_valid_tokens = {}
_last_login_ip = '无'


def generate_token() -> str:
    token = secrets.token_hex(32)
    expiry = time.time() + TOKEN_TTL_SECONDS
    with tokens_lock:
        _valid_tokens[token] = expiry
    return token


def verify_token(token: str) -> bool:
    with tokens_lock:
        expiry = _valid_tokens.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            _valid_tokens.pop(token, None)  # 惰性清理过期 token
            return False
        return True


def remove_token(token: str):
    with tokens_lock:
        _valid_tokens.pop(token, None)


def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        return {'code': 401, 'data': '未授权'}
    token = authorization[7:]
    if not verify_token(token):
        return {'code': 401, 'data': '未授权'}
    return None


def require_init():
    """校验浏览器是否已初始化，未初始化返回友好提示"""
    if not init:
        return {'code': 400, 'data': '浏览器未初始化，请先在首页初始化浏览器'}
    return None


# 定时任务存储
scheduled_tasks = {}  # 格式: {任务ID: job对象}
paused_tasks = {}     # 已停用任务: {任务ID: {'time':..., 'name':..., 'text':...}}
_pending_tasks = {}   # 启动时从磁盘加载、等待浏览器初始化后再注册的定时任务: {任务ID: {'time':..., 'name':..., 'text':...}}

# 任务持久化文件（默认与脚本同目录；可用环境变量 TASKS_FILE 覆盖，便于 Docker 挂载数据卷）
TASKS_FILE = os.environ.get(
    'TASKS_FILE',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.json')
)


def _job_to_meta(job) -> dict:
    """从 schedule 的 job 对象提取任务元数据，用于持久化"""
    name, text = '', None
    try:
        args = job.job_func.args
        if len(args) > 0:
            name = args[0]
        if len(args) > 1:
            text = args[1]
    except Exception:
        pass
    time_str = ''
    try:
        time_str = job.at_time.strftime('%H:%M')
    except Exception:
        pass
    return {'time': time_str, 'name': name, 'text': text}


def log(msg: str):
    """统一日志输出（带时间戳，写入容器日志 docker logs 可见）。"""
    try:
        print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True)
    except Exception:
        pass


def _save_tasks():
    """将当前定时任务（含已停用）持久化到 JSON 文件；须在 tasks_lock 内调用"""
    try:
        data = {
            'scheduled': {task_id: _job_to_meta(job) for task_id, job in scheduled_tasks.items()},
            'paused': dict(paused_tasks),
        }
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 任务持久化失败: {e}')


def _load_tasks():
    """启动时从 JSON 文件恢复任务：已停用任务直接恢复，定时任务等待浏览器初始化后再注册"""
    if not os.path.exists(TASKS_FILE):
        return
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        paused_tasks.clear()
        paused_tasks.update(data.get('paused', {}))
        _pending_tasks.clear()
        _pending_tasks.update(data.get('scheduled', {}))
        log(f'📂 已从磁盘恢复 {len(_pending_tasks)} 个定时任务、{len(paused_tasks)} 个已停用任务')
    except Exception as e:
        print(f'⚠️ 任务恢复失败: {e}')


def _restore_scheduled_tasks():
    """浏览器初始化成功后，把持久化的定时任务重新注册到 schedule；须在 tasks_lock 内调用"""
    for task_id, meta in list(_pending_tasks.items()):
        name = meta.get('name', '')
        play_time = meta.get('time', '')
        text = meta.get('text')
        if not name or not play_time:
            print(f'⚠️ 跳过无效任务 {task_id}')
            del _pending_tasks[task_id]
            continue
        msg = AiqingGongyu_text() if not text else text
        try:
            job = schedule.every().day.at(play_time).do(_scheduled_send, name, msg)
            scheduled_tasks[task_id] = job
            del _pending_tasks[task_id]
        except Exception as e:
            print(f'⚠️ 恢复定时任务失败 {task_id}: {e}')


_load_tasks()


# 定时线程
def _scheduled_send(name, text):
    """定时任务执行入口：调用发送并输出执行结果日志（供 schedule 调度）。

    入参保持 (name, text) 形态，与任务持久化/编辑解析逻辑一致。
    """
    preview = (text or '')[:30]
    # 浏览器未就绪时不执行（也不报错）：避免容器刚启动、还没点「初始化浏览器」时误判为发送失败
    if not (init and _driver_alive()):
        log(f'⏭️ 定时任务跳过（浏览器未初始化）→ 好友：{name}｜请先在首页点击「初始化浏览器」')
        return
    # 有人正在网页端远程操作（登录向导里的二次验证）时让路，避免打断人工操作
    if remote_control_active():
        log(f'⏭️ 定时任务跳过（正在远程操作浏览器/人工验证中）→ 好友：{name}｜本次不再重试')
        return
    # 页面被导航到别处时先拉回聊天页（否则一定发不出去）
    _ensure_douyin_page('定时任务执行前')
    # 抖音登录态失效时明确跳过，避免被记成"发送失败"让人误以为任务写错了
    if not _verify_login_state():
        log(f'⏭️ 定时任务跳过（抖音未登录/登录已失效）→ 好友：{name}｜请到「登录向导」重新登录')
        return
    _dismiss_browser_dialogs('定时任务执行前')
    log(f'⏰ 定时任务触发 → 好友：{name}')
    try:
        out = douyin.Send_Frinder(name, text)
        if getattr(out, 'is_bool', False):
            log(f'✅ 定时任务发送成功 → 好友：{name}｜内容：{preview}')
        else:
            log(f'❌ 定时任务发送失败 → 好友：{name}｜原因：{getattr(out, "string", "未知")}')
    except Exception as e:
        log(f'❌ 定时任务执行异常 → 好友：{name}｜错误：{e}')


def run_schedule():
    """后台线程运行定时任务"""
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            log(f'⚠️ 调度循环异常: {e}')
        time.sleep(1)


_scheduler_started = False
_scheduler_thread = None


def start_scheduler():
    """启动定时任务调度线程（幂等：只启动一次，避免重初始化时重复调度）"""
    global _scheduler_started, _scheduler_thread
    with init_lock:
        if _scheduler_started and _scheduler_thread and _scheduler_thread.is_alive():
            return None
        _scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
        _scheduler_thread.start()
        _scheduler_started = True
        log('调度器已启动（后台线程运行定时任务）')
    return _scheduler_thread


def _scheduler_alive():
    """调度线程是否存活（用于状态检测）"""
    return bool(_scheduler_thread and _scheduler_thread.is_alive())


start_time = datetime.now(timezone.utc)


# 抖音操作
@app.get('/Home')
def Home(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'time': start_time}


# 登录态探测用的页面标志 / Cookie（扫码登录成功后只能靠这些判断，不能只信内存标志位）
_LOGIN_PANEL_XPATH = '//*[@id="douyin_login_comp_flat_panel"]/picture'
_LOGIN_OK_XPATHS = (
    '//div[@class="conversationConversationListwrapper"]',  # 聊天页会话列表（登录后才加载）
    '//*[@id="douyin-header"]//img',                        # 顶部自己的头像
    '//*[@id="douyin_right_header"]//img',
)
_LOGIN_COOKIE_KEYS = ('sessionid', 'sessionid_ss', 'sid_tt')


def _detect_login_state():
    """主动探测抖音登录态（须在 driver_lock 内调用）。

    扫码登录成功后页面不会主动通知后端，必须实际看页面/Cookie，判定顺序：
      1) 出现登录面板 → 未登录；
      2) 出现会话列表或自己的头像 → 已登录；
      3) 兜底：持有抖音登录态 Cookie（sessionid 系列）且当前不在登录/通行证页 → 已登录。
    """
    # 先看当前页面：浏览器可能被临时导航到别的页面（例如用 VNC 打开了容器内的管理页），
    # 此时既看不到登录面板也读不到抖音 Cookie，不能据此判定"未登录"，保持既有状态即可。
    try:
        cur_url = driver.current_url or ''
    except Exception:
        cur_url = ''
    if cur_url and 'douyin.com' not in cur_url:
        return bool(Login_is_bool)

    cookies = {}
    try:
        for c in driver.get_cookies():
            cookies[c.get('name')] = c.get('value')
    except Exception:
        pass
    has_session = any(cookies.get(k) for k in _LOGIN_COOKIE_KEYS)

    try:
        driver.find_element(By.XPATH, _LOGIN_PANEL_XPATH)
        return False  # 登录面板还在 → 未登录
    except NoSuchElementException:
        pass
    except Exception:
        return bool(has_session)

    for xpath in _LOGIN_OK_XPATHS:
        try:
            driver.find_element(By.XPATH, xpath)
            return True
        except NoSuchElementException:
            continue
        except Exception:
            break

    try:
        url = (driver.current_url or '')
    except Exception:
        url = ''
    if has_session and 'login' not in url and 'passport' not in url:
        return True
    return False


def _verify_login_state():
    """校验抖音登录状态：以页面实际状态为准，并同步内存标志位。

    历史问题：早期实现只在 Login_is_bool 为真时才去核对页面，而**扫码登录成功这条路径没人置真**，
    于是"登录成功了却一直显示未登录"。现在每次都主动探测，状态变化时打日志。
    """
    global Login_is_bool
    if not _driver_alive():
        if Login_is_bool:
            Login_is_bool = False
            log('🔑 登录状态变更：浏览器会话不可用，已复位为未登录')
        return False
    try:
        with driver_lock:
            ok = _detect_login_state()
    except Exception as e:
        return bool(Login_is_bool)
    if ok != Login_is_bool:
        Login_is_bool = ok
        log('🔑 登录状态变更：' + ('已登录' if ok else '未登录（登录面板未通过 / 会话失效）'))
    return ok


def _driver_alive():
    """轻量探测 driver 是否仍可用（Chrome 崩溃/会话失效时返回 False）。"""
    global driver
    if not driver:
        return False
    try:
        with driver_lock:
            driver.current_url
        return True
    except Exception:
        return False


def _reset_driver_state():
    """复位浏览器/登录状态并释放 driver（供 Chrome 崩溃后重建）。"""
    global init, driver, douyin, Login_is_bool
    with init_lock:
        try:
            with driver_lock:
                if driver:
                    driver.quit()
        except Exception:
            pass
        driver = None
        douyin = None
        init = False
        Login_is_bool = False


def _create_browser_locked():
    """创建浏览器会话（调用方必须已持有 init_lock，RLock 可重入）。

    供 /Api/Init（首次初始化）与 /Api/ReInit（重新初始化）复用。
    """
    global init, driver, douyin, options

    try:
        options = unban_config()  # 每次新建，重试初始化不会叠加重复参数
        new_driver = webdriver.Chrome(service=service, options=options) if service else webdriver.Chrome(options=options)
        try:
            new_driver.set_window_size(1280, 720)
            new_driver.get('https://www.douyin.com/chat?isPopup=1')
        except Exception:
            try:
                new_driver.quit()  # 已创建但未就绪，释放避免僵尸 Chrome 累积
            except Exception:
                pass
            raise
        driver = new_driver
        douyin = Douyin(driver)
        init = True
        # 抖音页面加载后会尝试拉起 App，可能出现模态确认框（会吞掉页面输入），
        # 这里在几秒内多清几次，确保进入可用状态
        for _delay in (1.0, 2.5, 5.0):
            time.sleep(_delay)
            _dismiss_browser_dialogs('初始化后')
        # 无窗口管理器环境：主动把抖音窗口置顶并移到 (0,0)，避免被其它窗口（如 VNC 里的前端浏览器）遮挡
        try:
            subprocess.run(
                ['xdotool', 'search', '--name', 'douyin', 'windowraise', 'windowmove', '0', '0'],
                timeout=5, capture_output=True,
            )
        except Exception:
            pass
        with tasks_lock:
            _restore_scheduled_tasks()  # 恢复持久化的定时任务
            _save_tasks()
        start_scheduler()  # 启动调度线程（幂等）
        log('🌐 浏览器初始化成功（Chromium 已启动并打开抖音）')
        return {'code': 200, 'data': 'success'}
    except SessionNotCreatedException as e:
        log(f'❌ 浏览器会话创建失败：{e}')
        if "This version of ChromeDriver only supports" in str(e):
            return {'code': 400, 'data': '浏览器驱动与浏览器版本不匹配，请更新 chromedriver!'}
        if 'DevToolsActivePort' in str(e):
            return {'code': 400, 'data': '浏览器启动失败（多为登录资料目录残留锁），请点击「重新初始化浏览器」重试'}
        return {'code': 400, 'data': f'浏览器会话创建失败: {str(e)}'}
    except Exception as e:
        log(f'❌ 浏览器初始化失败：{e}')
        return {'code': 500, 'data': f'初始化失败: {str(e)}'}


@app.get('/Api/Init')  # 初始化浏览器
def Init(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err

    with init_lock:
        # Chrome 崩溃/会话失效后 init 仍是 True：探测到失效则复位，允许重建
        if init and _driver_alive():
            return {'code': 200, 'data': 'init Repeated!'}
        if init:
            _reset_driver_state()
        return _create_browser_locked()


@app.get('/Api/ReInit')  # 重新初始化浏览器（强制关闭现有会话并重建）
def ReInit(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err

    log('🔄 收到「重新初始化浏览器」请求，正在关闭现有浏览器会话…')
    _reset_driver_state()  # 无论当前是否可用，先彻底释放，再重建
    with init_lock:
        return _create_browser_locked()


@app.get('/Api/GetInit')  # 获取初始化状态
def GetInit(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 准确性：已初始化且 driver 仍可用才算 Yes（浏览器崩溃/会话失效时返回 No）
    alive = bool(init) and _driver_alive()
    return {'code': 200, 'data': 'Yes' if alive else 'No'}


@app.get('/Api/GetStatus')  # 综合运行状态（浏览器 / 登录 / 调度器 / 任务数）
def GetStatus(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    browser_ok = bool(init) and _driver_alive()
    login_ok = browser_ok and _verify_login_state()
    with tasks_lock:
        active = len(scheduled_tasks)
        paused = len(paused_tasks)
    return {
        'code': 200,
        'data': {
            'browser': 'Yes' if browser_ok else 'No',
            'login': 'Yes' if login_ok else 'No',
            'scheduler': 'Yes' if _scheduler_alive() else 'No',
            'task_count': active,
            'paused_count': paused,
            'uptime_seconds': int((datetime.now(timezone.utc) - start_time).total_seconds()),
        },
    }


@app.get('/Api/GetSaveSession')  # 是否保存抖音登录数据（Cookie）
def GetSaveSession(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': bool(_config.get('save_session', False))}


@app.post('/Api/SetSaveSession')  # 设置是否保存抖音登录数据（持久化到配置文件）
def SetSaveSession(payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    body = payload or {}
    enabled = bool(body.get('enabled'))
    _config['save_session'] = enabled
    _save_config()
    log(f'⚙️ 设置变更：保存登录数据（Cookie）→ {"开启" if enabled else "关闭"}（重新初始化浏览器后生效）')
    return {'code': 200, 'data': enabled}


@app.post('/Api/login')  # 登录 传入 Base64Cookie
def Login(payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    global Login_is_bool
    cooke = (payload or {}).get('cooke')  # 前端发送 {"cooke": "base64..."}，与其它 POST 接口一致
    if cooke:
        try:
            cookie_json = base64.b64decode(cooke).decode('utf-8')
            cookie_data = json.loads(cookie_json)
        except Exception as e:
            return {'code': 404, 'data': f'login-error-cookie parse error: {str(e)}'}
        with driver_lock:
            try:
                for cookie in cookie_data:
                    driver.add_cookie(cookie)
                driver.refresh()
            except Exception as e:
                return {'code': 404, 'data': f'login-error-cookie parse error: {str(e)}'}
            try:
                login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
                login_type = login_type_element.text
                return {'code': 404, 'data': 'login-error-cooker cant login'}
            except NoSuchElementException:
                Login_is_bool = True
                log('🔑 登录状态变更：Cookie 登录成功')
                return {'code': 200, 'data': 'ok'}
    else:
        return {'code': 404, 'data': 'login-error-not cooker'}  # # @#z


@app.get('/Api/Pnglogin')  # 扫码登录
def PngLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    global Login_is_bool
    try:
        with driver_lock:
            if driver.get_cookies():
                driver.refresh()
                try:
                    login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
                    login_type = login_type_element.text
                    driver.refresh()
                    return {'code': 200, 'data': 'No'}
                except NoSuchElementException:
                    Login_is_bool = True
                    log('🔑 登录状态变更：Cookie 登录成功')
                    return {'code': 200, 'data': 'ok'}
            else:
                return {'code': 200, 'data': 'No'}  # # @#z
    except Exception as e:
        # 页面处于异常状态（驱动异常/页面崩溃）时自动刷新页面恢复
        log(f'♻️ 扫码登录检测异常（{e}），自动刷新页面')
        _recover_douyin_page('扫码登录检测异常')
        return {'code': 200, 'data': 'No', 'msg': '页面已自动刷新，请重新点击扫码登录'}


@app.get('/Api/GetLogin')  # 获取登录
def GetLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 准确性：不只读取标记，而是实际校验一次（浏览器可用 + 页面无登录面板）
    return {'code': 200, 'data': 'Yes' if _verify_login_state() else 'No'}


@app.get('/Api/login/Init/GetLoginPng')  # 获取登录扫码
def GetLoginPng(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    last_error = ''
    # 最多两次：第一次失败会自动刷新页面再试一次
    for attempt in (1, 2):
        try:
            with driver_lock:
                Douyin.LoginInit(douyin)
                try:
                    driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div/p[1]')
                    img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
                    img_element.click()
                except Exception:
                    pass
                img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
                login_src = img_element.get_attribute('src')
                try:
                    is_rust = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div')
                    is_rust.click()
                    time.sleep(5)
                    img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
                    login_src = img_element.get_attribute('src')
                except Exception:
                    pass
                if login_src:
                    if attempt == 2:
                        log('♻️ 自动刷新页面后成功获取登录二维码')
                    return {'code': 200, 'data': login_src}
                last_error = 'cant find LoginPng src attribute'
        except NoSuchElementException:
            last_error = 'cant find img element'
        except Exception as e:
            last_error = str(e)

        # 第一次失败：自动刷新页面（恢复异常状态）后重试
        if attempt == 1:
            log(f'♻️ 获取登录二维码失败（{last_error}），自动刷新页面后重试…')
            _recover_douyin_page('二维码获取失败')

    return {'code': 404, 'data': f'获取登录二维码失败（已自动刷新页面重试）：{last_error or "页面异常"}'}


@app.post('/Api/login/Init/GetCooker')  # 获取cooke
def GetCooke(request: Request, payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    body = payload or {}
    password = str(body.get('password') or '')
    # 与后台登录共用同一套失败限流，避免绕过登录接口暴力破解密码
    ip = _client_ip(request)
    if _is_login_locked(ip):
        return {'code': 429, 'data': f'失败次数过多，请 {_LOGIN_LOCK_WINDOW // 60} 分钟后再试'}
    # 验证密码（加盐哈希）
    if not _verify_password(password, _password_hash):
        _record_login_fail(ip)
        return {'code': 400, 'data': '密码错误'}
    with login_attempts_lock:
        _login_attempts.pop(ip, None)  # 密码正确时清零失败记录
    if Login_is_bool:
        with driver_lock:
            cooke = driver.get_cookies()
        cookie_json = json.dumps(cooke)
        cookie_base64 = base64.b64encode(cookie_json.encode('utf-8')).decode('utf-8')
        return {'code': 200, 'data': {'cooke': cookie_base64}}
    else:
        return {'code': 400, 'data': '未登录'}


@app.get('/Api/GetFriendsList')  # 获取好友列表
def GetFrindesList(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    try:
        friends_list = douyin.Updara_FrinderList()
        dicts = {}
        if len(friends_list) == 0:
            # 空列表是正常状态，返回 200 + 空列表，避免前端每次误弹「暂无好友」错误
            return {'code': 200, 'data': {'count': 0, 'list': dicts}}
        for v in friends_list:
            dicts[v.username] = [v.avatar, v.fire]
        return {'code': 200, 'data': {'count': len(friends_list), 'list': dicts}}
    except Exception as e:
        return {'code': 404, 'data': str(e)}


@app.post('/Api/Send')  # 发送信息
def Send(payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    body = payload or {}
    name = str(body.get('name') or '').strip()
    text = str(body.get('text') or '')
    # Send_Frinder 内部已调用 Updara_FrinderList，这里不再重复全量爬取
    out = Douyin.Send_Frinder(douyin, name, text)
    if out.is_bool:
        log(f'💬 手动发送消息 → 好友：{name}｜内容：{(text or "")[:30]}')
        return {'code': 200, 'data': 'Send successfully'}
    else:
        return {'code': 404, 'data': out.string}


_self_avatar_cache = ''  # 当前登录抖音账号头像 URL 缓存


def _extract_self_avatar():
    """获取当前登录抖音账号的头像 URL（需在 driver_lock 内调用）。

    优先级：① 页面 JSON（userInfo 的头像字段，登录后即可用）
            ② DOM 中的头像 img（发消息时自己头像会渲染在聊天气泡旁）
            ③ 上次缓存值
    命中后写入缓存，后续调用直接返回。
    """
    global _self_avatar_cache
    js = (
        "var d = window._ROUTER_DATA || window.__INITIAL_STATE__ || null;"
        "if (!d) return null;"
        "var hit = null;"
        "(function walk(o){"
        "  if (!o || typeof o !== 'object' || hit) return;"
        "  if (Array.isArray(o)) { for (var i=0;i<o.length;i++) walk(o[i]); return; }"
        "  var ks = Object.keys(o);"
        "  for (var i=0;i<ks.length;i++){"
        "    var k = ks[i], v = o[k];"
        "    if ((k === 'userInfo' || k === 'user_info') && v && typeof v === 'object' && typeof v.nickname === 'string') {"
        "      var names = ['avatar_thumb','avatar_larger','avatar_168x168','avatar_300x300','avatar_medium','avatar_100x100'];"
        "      for (var j=0;j<names.length;j++){"
        "        var a = v[names[j]];"
        "        if (typeof a === 'string' && a) { hit = a; return; }"
        "        if (a && a.url_list && a.url_list.length) { hit = a.url_list[0]; return; }"
        "      }"
        "      var direct = v.avatarUri || v.avatarUrl || v.avatar_uri || v.avatar_url;"
        "      if (typeof direct === 'string' && direct) { hit = direct; return; }"
        "      var ks2 = Object.keys(v);"
        "      for (var m=0;m<ks2.length;m++){"
        "        if (ks2[m].toLowerCase().indexOf('avatar') >= 0) {"
        "          var av = v[ks2[m]];"
        "          if (typeof av === 'string' && av) { hit = av; return; }"
        "          if (av && av.url_list && av.url_list.length) { hit = av.url_list[0]; return; }"
        "        }"
        "      }"
        "      return;"
        "    }"
        "    walk(v);"
        "  }"
        "})(d);"
        "return hit;"
    )
    try:
        url = driver.execute_script(js)
        if url:
            _self_avatar_cache = str(url)
            return _self_avatar_cache
    except Exception:
        pass
    # ② DOM 兜底：聊天消息区里自己的头像（取最后一张抖音头像 img）
    try:
        imgs = driver.find_elements(By.XPATH, '//img[contains(@src,"douyinpic.com")]')
        for el in reversed(imgs):
            src = el.get_attribute('src')
            if src and 'avatar' in src:
                _self_avatar_cache = src
                return src
    except Exception:
        pass
    # ③ 最后返回缓存
    return _self_avatar_cache or ''


def _extract_nickname():
    """从页面数据中提取当前登录用户名。

    优先读取页面内注入的 JSON 数据（window._ROUTER_DATA / __INITIAL_STATE__），
    比直接正则硬挖 HTML 更抗抖音前端改版；最后回退到旧的正则方式。
    需在 driver_lock 内调用。
    """
    js = (
        "var d = window._ROUTER_DATA || window.__INITIAL_STATE__ || null;"
        "if (!d) return null;"
        "var hit = null;"
        "(function walk(o){"
        "  if (!o || typeof o !== 'object' || hit) return;"
        "  if (Array.isArray(o)) { for (var i=0;i<o.length;i++) walk(o[i]); return; }"
        "  var ks = Object.keys(o);"
        "  for (var i=0;i<ks.length;i++){"
        "    var k = ks[i], v = o[k];"
        "    if ((k === 'userInfo' || k === 'user_info') && v && typeof v === 'object' && typeof v.nickname === 'string'){ hit = v.nickname; return; }"
        "    walk(v);"
        "  }"
        "})(d);"
        "return hit;"
    )
    try:
        nickname = driver.execute_script(js)
        if nickname:
            return str(nickname)
        json_text = driver.execute_script(
            "var d = window._ROUTER_DATA || window.__INITIAL_STATE__ || null;"
            "return d ? JSON.stringify(d) : null;"
        )
        if json_text:
            m = re.search(r'"nickname"\s*:\s*"([^"]+)"', json_text)
            if m:
                return m.group(1)
    except Exception:
        pass
    # 回退：旧的 HTML 源码正则（兼容旧版页面）
    match = re.search(r'\\"nickname\\":\\"([^\\"]+)\\"', driver.page_source)
    if match:
        text = match.group(0)
        clean = text.replace('\\"', '"')
        try:
            data = json.loads('{' + clean + '}')
            return data['nickname']
        except Exception:
            return None
    return None


@app.get('/Api/GetUserInfo')  # 获取当前登录抖音账号信息（昵称 + 头像）
def GetUserInfoAll(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    if not _verify_login_state():
        return {'code': 400, 'data': '未登录'}
    with driver_lock:
        nickname = _extract_nickname() or ''
        avatar = _extract_self_avatar() or ''
    return {'code': 200, 'data': {'nickname': nickname, 'avatar': avatar}}


@app.get('/Api/GetUsername')  # 获取用户名
def GetUserInfo(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    if Login_is_bool:
        with driver_lock:
            nickname = _extract_nickname()
        if nickname:
            return {'code': 200, 'data': nickname}
        else:
            return {'code': 400, 'data': '已登录,但未获取到用户名'}
    else:
        return {'code': 400, 'data': '未登录'}


@app.get('/Api/GetScrlk')  # 获取截图
def GetScrlk(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    try:
        with driver_lock:
            img_bytes = driver.get_screenshot_as_png()
        img_data = base64.b64encode(img_bytes).decode('utf-8')
        return {'code': 200, 'data': img_data}
    except Exception as e:
        return {'code': 400, 'data': f'截图错误:{e}'}


# ============================================================
# 远程画面（CDP 画面串流 + 输入转发）—— 登录向导使用
#
# 不依赖 noVNC：直接通过 Chromium 的 DevTools 协议把画面（JPEG 帧）推给网页，
# 并把网页上的鼠标/键盘事件用 Input.* 命令回放到浏览器（trusted 事件，
# 画面里可直接点击完成二次验证）。DevTools 端口由 chromedriver 分配且仅监听 127.0.0.1。
# ============================================================
_screen_tickets = {}                 # 一次性连接票据 -> 过期时间戳
_screen_tickets_lock = threading.Lock()
_remote_control_lock = threading.Lock()
_remote_control_active = False       # 是否有人正在网页端远程操作浏览器
_SCREEN_TICKET_TTL = 30              # 票据有效期（秒）
_cdp_msg_id = 0
_cdp_id_lock = threading.Lock()
_last_remote_input_at = 0.0          # 最近一次收到远程输入的时间（用于避免清弹窗打扰用户操作）
_remote_input_lock = threading.Lock()


def _mark_remote_input():
    global _last_remote_input_at
    with _remote_input_lock:
        _last_remote_input_at = time.time()


def _remote_input_recent(window=1.5):
    with _remote_input_lock:
        return (time.time() - _last_remote_input_at) < window


def _cdp_id():
    global _cdp_msg_id
    with _cdp_id_lock:
        _cdp_msg_id += 1
        return _cdp_msg_id


def _issue_screen_ticket():
    ticket = secrets.token_urlsafe(24)
    now = time.time()
    with _screen_tickets_lock:
        for key in [k for k, exp in _screen_tickets.items() if exp < now]:
            _screen_tickets.pop(key, None)
        _screen_tickets[ticket] = now + _SCREEN_TICKET_TTL
    return ticket


def _consume_screen_ticket(ticket):
    """票据一次性使用：校验通过即删除（WebSocket 握手无法携带 Authorization 头）。"""
    if not ticket:
        return False
    with _screen_tickets_lock:
        exp = _screen_tickets.pop(ticket, None)
    return bool(exp and exp >= time.time())


def _set_remote_active(active):
    global _remote_control_active
    with _remote_control_lock:
        _remote_control_active = bool(active)


def remote_control_active():
    """有人远程操作时，定时任务应让路（否则会打断人工验证）。"""
    with _remote_control_lock:
        return _remote_control_active


def _vnc_enabled():
    return os.environ.get('VNC_ENABLED', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _dismiss_browser_dialogs(reason=''):
    """清掉 Chromium 的模态弹窗（如"是否允许打开 xdg-open"的外部协议框）。

    抖音页面会尝试用 snssdk1128:// 之类的自定义协议拉起 App，Chromium 默认弹出**模态**确认框；
    该弹窗会吞掉页面上的所有鼠标/键盘输入（远程操作与自动化都会被卡住），必须主动清掉。
    弹窗属于浏览器 UI，CDP 的 Input.* 打不到它，所以用 xdotool 在 X 层发 Esc。
    """
    if not SHOW_BROWSER or not os.environ.get('DISPLAY'):
        return
    try:
        # 必须先把浏览器窗口激活，否则 Esc 落到别的窗口上不起作用
        subprocess.run(['xdotool', 'search', '--name', 'douyin',
                        'windowactivate', '--sync'],
                       timeout=5, capture_output=True)
    except Exception:
        pass
    try:
        subprocess.run(['xdotool', 'key', '--clearmodifiers', 'Escape'],
                       timeout=5, capture_output=True)
        if reason:
            log(f'🧹 已清理浏览器模态弹窗（{reason}）')
    except Exception:
        pass


DOUYIN_CHAT_URL = 'https://www.douyin.com/chat?isPopup=1'


def _recover_douyin_page(reason=''):
    """页面异常（元素找不到 / 停在别的页面）时把浏览器拉回抖音聊天页并清理模态弹窗。

    用于"获取登录二维码""扫码登录"等操作失败后的自动恢复：
    先导航回聊天页，再重试一次，避免用户看到 cant find img element 这类报错后无从下手。
    """
    try:
        with driver_lock:
            driver.get(DOUYIN_CHAT_URL)
        time.sleep(2)
        _dismiss_browser_dialogs(reason or '页面恢复')
        log(f'♻️ 已自动刷新抖音页面（{reason or "页面恢复"}）')
        return True
    except Exception as e:
        log(f'⚠️ 自动刷新页面失败：{e}')
        return False


def _ensure_douyin_page(reason=''):
    """确保浏览器停在抖音聊天页：被导航到别处时自动拉回，避免自动化失效。

    须在 driver_lock 之外调用。返回 True 表示当前已在抖音页。
    """
    try:
        with driver_lock:
            url = driver.current_url or ''
    except Exception:
        return False
    if 'douyin.com' in url:
        return True
    log(f'↩️ 浏览器当前不在抖音页（{url[:60]}），自动拉回聊天页（{reason or "自动恢复"}）')
    return _recover_douyin_page(reason or '自动拉回聊天页')


def _viewport_info():
    """当前页面视口尺寸（CSS 像素）与缩放系数，前端据此换算鼠标坐标。"""
    if not (init and _driver_alive()):
        return None
    try:
        with driver_lock:
            width, height, dpr = driver.execute_script(
                'return [window.innerWidth, window.innerHeight, window.devicePixelRatio || 1]')
        return {
            'width': int(width),
            'height': int(height),
            'dpr': float(dpr or 1),
            'scale': float(SCALE_FACTOR or 1),
        }
    except Exception:
        return None


def _page_info():
    """当前浏览器页面标题与地址（登录向导用于提示"现在画面里是什么"）。"""
    if not (init and _driver_alive()):
        return None
    try:
        with driver_lock:
            return {'title': driver.title or '', 'url': driver.current_url or ''}
    except Exception:
        return None


def _devtools_ws_url():
    """取当前页面目标的 DevTools WebSocket 地址（用于 CDP 串流与输入回放）。"""
    try:
        caps = getattr(driver, 'capabilities', None) or {}
        addr = str(((caps.get('goog:chromeOptions') or {}).get('debuggerAddress')) or '').strip()
        if not addr:
            return None
        with urllib.request.urlopen(f'http://{addr}/json/list', timeout=5) as resp:
            targets = json.load(resp)
        pages = [t for t in targets if t.get('type') == 'page' and t.get('webSocketDebuggerUrl')]
        if not pages:
            return None
        page = next((t for t in pages if 'douyin.com' in str(t.get('url') or '')), pages[0])
        return page['webSocketDebuggerUrl']
    except Exception as e:
        log(f'⚠️ 获取 DevTools 调试地址失败：{e}')
        return None


_KEY_CODES = {
    'Enter': (13, 'Enter'), 'Tab': (9, 'Tab'), 'Backspace': (8, 'Backspace'),
    'Escape': (27, 'Escape'), 'Delete': (46, 'Delete'),
    'ArrowLeft': (37, 'ArrowLeft'), 'ArrowUp': (38, 'ArrowUp'),
    'ArrowRight': (39, 'ArrowRight'), 'ArrowDown': (40, 'ArrowDown'),
}


def _input_commands(msg):
    """把前端消息翻译成一组 CDP Input 命令。"""
    kind = (msg or {}).get('t')
    if kind == 'mouse':
        x, y = float(msg.get('x') or 0), float(msg.get('y') or 0)
        action = msg.get('a')
        button = msg.get('b') or 'left'
        if action == 'down':
            return [{'method': 'Input.dispatchMouseEvent', 'params': {
                'type': 'mousePressed', 'x': x, 'y': y, 'button': button,
                'buttons': 1, 'clickCount': 1}}]
        if action == 'move':
            # drag=1 表示按住左键拖动：拖动过程中必须保持 buttons=1
            return [{'method': 'Input.dispatchMouseEvent', 'params': {
                'type': 'mouseMoved', 'x': x, 'y': y, 'button': 'none',
                'buttons': 1 if msg.get('drag') else 0}}]
        if action == 'up':
            return [{'method': 'Input.dispatchMouseEvent', 'params': {
                'type': 'mouseReleased', 'x': x, 'y': y, 'button': button,
                'buttons': 0, 'clickCount': 1}}]
        return []
    if kind == 'touch':
        # 触摸设备（手机/平板）走 CDP 触摸事件，比合成鼠标更贴近真实操作
        action = msg.get('a')
        x, y = float(msg.get('x') or 0), float(msg.get('y') or 0)
        if action == 'start':
            return [{'method': 'Input.dispatchTouchEvent', 'params': {
                'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]}}]
        if action == 'move':
            return [{'method': 'Input.dispatchTouchEvent', 'params': {
                'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y}]}}]
        if action == 'end':
            return [{'method': 'Input.dispatchTouchEvent', 'params': {
                'type': 'touchEnd', 'touchPoints': []}}]
        return []
    if kind == 'wheel':
        return [{'method': 'Input.dispatchMouseEvent', 'params': {
            'type': 'mouseWheel', 'x': float(msg.get('x') or 0), 'y': float(msg.get('y') or 0),
            'deltaX': float(msg.get('dx') or 0), 'deltaY': float(msg.get('dy') or 0)}}]
    if kind == 'text':
        text = str(msg.get('text') or '')
        return [{'method': 'Input.insertText', 'params': {'text': text}}] if text else []
    if kind == 'key':
        key = str(msg.get('key') or '')
        code, name = _KEY_CODES.get(key, (None, None))
        if code is None:
            return []
        return [
            {'method': 'Input.dispatchKeyEvent', 'params': {
                'type': 'rawKeyDown', 'key': name, 'code': name,
                'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code}},
            {'method': 'Input.dispatchKeyEvent', 'params': {
                'type': 'keyUp', 'key': name, 'code': name,
                'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code}},
        ]
    return []


@app.get('/Api/Screen/Info')  # 远程画面：可用性与视口信息
def ScreenInfo(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': {
        'browser': bool(init and _driver_alive()),
        'viewport': _viewport_info(),
        'page': _page_info(),
        'remote_active': remote_control_active(),
        'vnc_enabled': _vnc_enabled(),
        'stream_available': websockets is not None,
    }}


@app.get('/Api/Screen/Ticket')  # 远程画面：签发一次性连接票据
def ScreenTicket(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    if websockets is None:
        return {'code': 500, 'data': '服务端缺少 websockets 依赖，无法建立画面串流'}
    if not (init and _driver_alive()):
        return {'code': 400, 'data': '浏览器未初始化，请先在首页点击「初始化浏览器」'}
    if remote_control_active():
        return {'code': 409, 'data': '已有其它页面正在远程操作浏览器，请先关闭那个页面'}
    return {'code': 200, 'data': {'ticket': _issue_screen_ticket(), 'expires_in': _SCREEN_TICKET_TTL}}


@app.websocket('/Api/Screen/Stream')  # 远程画面：CDP 画面串流 + 输入转发
async def ScreenStream(websocket: WebSocket):
    if not _consume_screen_ticket(websocket.query_params.get('ticket') or ''):
        await websocket.close(code=4401)  # 票据无效 / 过期 / 已使用
        return
    if websockets is None or not (init and _driver_alive()):
        await websocket.close(code=4400)
        return

    ws_url = await asyncio.to_thread(_devtools_ws_url)
    if not ws_url:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    viewport = await asyncio.to_thread(_viewport_info) or {}
    await websocket.send_json({'t': 'ready', 'viewport': viewport})
    _set_remote_active(True)
    await asyncio.to_thread(_dismiss_browser_dialogs, '远程画面会话开始')
    log('🖥️ 远程画面会话已连接（CDP 串流开始）')

    async def dialog_watchdog():
        """串流期间定期清弹窗：用户在画面里点击可能再次触发外部协议确认框。

        若最近 1.5 秒内收到过远程输入，说明用户正在操作且输入是通的，此时不打扰
        （弹窗一旦出现会吞掉输入，届时自然不再有输入，下一轮就会清理）。
        """
        while True:
            await asyncio.sleep(3)
            if _remote_input_recent():
                continue
            await asyncio.to_thread(_dismiss_browser_dialogs)

    async def cdp_to_client(cdp):
        """唯一读取 CDP 连接的任务（同一条连接不允许并发读取，否则帧会被抢走）。"""
        async for raw in cdp:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            # 命令出错（参数不合法等）只记日志，不影响串流
            if msg.get('error'):
                log(f'⚠️ CDP 命令执行出错：{msg.get("error")}')
                continue
            if msg.get('method') != 'Page.screencastFrame':
                continue
            params = msg.get('params') or {}
            # 必须先 ack，否则浏览器不会再推下一帧
            await cdp.send(json.dumps({
                'id': _cdp_id(), 'method': 'Page.screencastFrameAck',
                'params': {'sessionId': params.get('sessionId')}}))
            data = params.get('data')
            if data:
                await websocket.send_bytes(base64.b64decode(data))

    async def client_to_cdp(cdp):
        first = True
        while True:
            msg = await websocket.receive_json()
            _mark_remote_input()
            cmds = _input_commands(msg)
            if first:
                log(f'🖥️ 远程输入通道就绪：首个消息 type={msg.get("t")} → {len(cmds)} 条 CDP 命令')
                first = False
            for cmd in cmds:
                cmd['id'] = _cdp_id()
                await cdp.send(json.dumps(cmd))

    try:
        async with websockets.connect(ws_url, max_size=None, open_timeout=10,
                                      ping_interval=20, ping_timeout=20) as cdp:
            await cdp.send(json.dumps({'id': _cdp_id(), 'method': 'Page.enable'}))
            await cdp.send(json.dumps({
                'id': _cdp_id(), 'method': 'Page.startScreencast',
                'params': {
                    'format': 'jpeg', 'quality': 60, 'everyNthFrame': 1,
                    'maxWidth': int(viewport.get('width') or 1280),
                    'maxHeight': int(viewport.get('height') or 720),
                }}))
            tasks = [asyncio.create_task(cdp_to_client(cdp)),
                     asyncio.create_task(client_to_cdp(cdp)),
                     asyncio.create_task(dialog_watchdog())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception() if not task.cancelled() else None
                if exc:
                    log(f'⚠️ 远程画面任务异常：{type(exc).__name__}: {exc}')
            for task in tasks:
                task.cancel()
            try:
                await cdp.send(json.dumps({'id': _cdp_id(), 'method': 'Page.stopScreencast'}))
            except Exception:
                pass
    except Exception as e:
        log(f'⚠️ 远程画面会话异常：{e}')
    finally:
        _set_remote_active(False)
        log('🖥️ 远程画面会话已结束')
        try:
            await websocket.close()
        except Exception:
            pass


@app.get('/Api/DieLogin')  # 取消登录
def DieLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    global Login_is_bool
    with driver_lock:
        driver.delete_all_cookies()
        driver.refresh()
    Login_is_bool = False
    log('🚪 登录状态变更：已清除 Cookie（强制退出登录）')
    return {'code': 200, 'data': '已清除Cooke'}


@app.get('/Api/LoginPhone')  # 验证码登录
def authorization(areacode: str, phone: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    try:
        with driver_lock:
            Douyin.LoginInit(douyin)
            areacode_value = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_normal_input_id"]/div[1]/div/input')
            areacode_value.clear()
            areacode_value.send_keys(areacode.strip())
            inp = driver.find_element(By.XPATH, '//*[@id="normal-input"]')
            inp.send_keys(phone)
            span = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_button_input_id"]/span')
            span.click()
            time.sleep(2)
            if span.text.strip() == '获取验证码':
                return {'code': 400, 'data': '验证码发送失败'}
            else:
                return {'code': 200, 'data': '验证码发送成功'}
    except Exception as e:
        return {'code': 400, 'data': str(e)}


@app.get('/Api/LoginPhoneInput')  # 验证码登录 2 输入验证码
def authorizations(code: str, authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    try:
        with driver_lock:
            inp = driver.find_element(By.XPATH, '//*[@id="button-input"]')
            inp.send_keys(code)
            button = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_btn_id"]')
            button.click()
            time.sleep(2)
            try:
                login_div = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
                return {'code': 400, 'data': '登录失败'}
            except:
                Login_is_bool = True
                log('🔑 登录状态变更：验证码登录成功')
                return {'code': 200, 'data': '登录成功'}
    except Exception as e:
        return {'code': 400, 'data': str(e)}


@app.get('/Api/LoginDebug')
def LoginDebug(authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    if Login_is_bool == False:
        Login_is_bool = True
        return {'code': 200, 'data': 'OK'}
    else:
        return {'code': 400, 'data': '已是登录状态,无需设定'}


# 定时任务操作
@app.post('/Time/add')
def add_time(payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    body = payload or {}
    time = str(body.get('time') or '')
    name = str(body.get('name') or '').strip()
    text = body.get('text')
    # 快速去重检查（含已停用），避免重复任务
    with tasks_lock:
        for task_id in list(scheduled_tasks.keys()) + list(paused_tasks.keys()):
            parts = task_id.split('_', 1)
            if len(parts) == 2 and parts[1] == name:
                return {'code': 400, 'data': f'好友 {name} 已有定时任务，请先删除或修改'}

    temp = douyin.Find_Friends(name)
    if not temp.is_bool:
        return {'code': 404, 'data': temp.string}

    play_time = format_time(time)
    msg = AiqingGongyu_text() if not text else text  # 空串也视为未自定义，避免注册发空消息
    task_id = f"{play_time}_{name}"

    # 原子化：再次去重 + 注册任务 + 持久化
    with tasks_lock:
        for existing_id in list(scheduled_tasks.keys()) + list(paused_tasks.keys()):
            parts = existing_id.split('_', 1)
            if len(parts) == 2 and parts[1] == name:
                return {'code': 400, 'data': f'好友 {name} 已有定时任务，请先删除或修改'}
        job = schedule.every().day.at(play_time).do(_scheduled_send, name, msg)
        scheduled_tasks[task_id] = job
        _save_tasks()
    log(f'📌 新增定时任务 → 好友：{name}｜时间：{play_time}｜内容：{(msg or "")[:30]}')
    return {'code': 200, 'data': f'已添加定时任务: {play_time}', 'task_id': task_id}


@app.get('/Time/del')
def del_time(task_id: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """根据任务ID删除定时任务"""
    with tasks_lock:
        if task_id in scheduled_tasks:
            job = scheduled_tasks[task_id]
            schedule.cancel_job(job)
            del scheduled_tasks[task_id]
            _save_tasks()
            log(f'🗑️ 删除定时任务 → {task_id}')
            return {'code': 200, 'data': f'已删除任务: {task_id}'}
        elif task_id in paused_tasks:
            del paused_tasks[task_id]
            _save_tasks()
            log(f'🗑️ 删除定时任务 → {task_id}')
            return {'code': 200, 'data': f'已删除任务: {task_id}'}
        else:
            return {'code': 404, 'data': '任务ID不存在'}


@app.get('/Time/edit')
def edit_time(name: str, new_time: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    """修改指定好友的定时任务时间"""
    # 读取旧任务信息（短锁，只做快速读）
    with tasks_lock:
        old_task_id = None
        old_job = None
        for task_id, job in scheduled_tasks.items():
            parts = task_id.split('_', 1)
            if len(parts) == 2 and parts[1] == name:
                old_task_id = task_id
                old_job = job
                break

        if not old_task_id:
            return {'code': 404, 'data': f'好友 {name} 没有定时任务'}

        # 解析旧任务信息
        parts = old_task_id.split('_', 1)
        old_time = parts[0] if len(parts) == 2 else ""

        # 保留原有消息内容（自定义消息不被每日名言覆盖）
        msg = None
        try:
            args = old_job.job_func.args
            if len(args) > 1:
                msg = args[1]
        except Exception:
            msg = None

    # 计算新时间；若与旧时间相同则不做任何变更，避免任务被误删（幽灵任务）
    new_play_time = format_time(new_time)
    if new_play_time == old_time:
        return {'code': 200, 'data': '执行时间未变化，任务保持不变', 'task_id': old_task_id}

    if not msg:
        msg = AiqingGongyu_text()

    # 原子化：再次确认任务仍在 + 取消旧任务 + 创建新任务 + 持久化
    with tasks_lock:
        if old_task_id not in scheduled_tasks:
            return {'code': 404, 'data': f'好友 {name} 没有定时任务'}
        schedule.cancel_job(scheduled_tasks[old_task_id])

        # 创建新任务
        new_job = schedule.every().day.at(new_play_time).do(_scheduled_send, name, msg)

        # 生成新任务ID并替换
        new_task_id = f"{new_play_time}_{name}"
        scheduled_tasks[new_task_id] = new_job
        del scheduled_tasks[old_task_id]
        _save_tasks()

    log(f'🕒 修改定时任务时间 → 好友：{name}｜{old_time} → {new_play_time}')
    return {
        'code': 200,
        'data': f'已将 {name} 的定时任务从 {old_time} 修改为 {new_play_time}',
        'old_time': old_time,
        'new_time': new_play_time,
        'task_id': new_task_id
    }


@app.get('/Time/getlist')
def get_time_list(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """获取当前所有定时任务列表"""
    tasks = []
    with tasks_lock:
        for task_id, job in list(scheduled_tasks.items()):
            # 解析任务ID获取信息
            parts = task_id.split('_', 1)
            if len(parts) == 2:
                time_str, name = parts
                tasks.append({
                    'task_id': task_id,
                    'time': time_str,
                    'name': name,
                    'active': True,
                    'next_run': str(job.next_run) if job.next_run else None
                })
        for task_id, info in list(paused_tasks.items()):
            tasks.append({
                'task_id': task_id,
                'time': info.get('time', ''),
                'name': info.get('name', ''),
                'active': False,
                'next_run': None
            })
    return {'code': 200, 'data': {'count': len(tasks), 'tasks': tasks}}


@app.get('/Time/pause')  # 停用定时任务
def pause_time(task_id: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    with tasks_lock:
        job = scheduled_tasks.get(task_id)
        if not job:
            return {'code': 404, 'data': '任务ID不存在或已停用'}
        parts = task_id.split('_', 1)
        time_str = parts[0] if len(parts) == 2 else ''
        name = parts[1] if len(parts) == 2 else ''
        text = None
        try:
            args = job.job_func.args
            if len(args) > 1:
                text = args[1]
        except Exception:
            text = None
        schedule.cancel_job(job)
        del scheduled_tasks[task_id]
        paused_tasks[task_id] = {'time': time_str, 'name': name, 'text': text}
        _save_tasks()
    log(f'⏸️ 停用定时任务 → {task_id}')
    return {'code': 200, 'data': f'已停用任务: {task_id}'}


@app.get('/Time/enable')  # 启用定时任务
def enable_time(task_id: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    init_err = require_init()
    if init_err:
        return init_err
    with tasks_lock:
        info = paused_tasks.get(task_id)
        if not info:
            return {'code': 404, 'data': '任务ID不存在或未停用'}
        play_time = info.get('time', '')
        name = info.get('name', '')
        text = info.get('text')
        msg = AiqingGongyu_text() if not text else text
        try:
            job = schedule.every().day.at(play_time).do(_scheduled_send, name, msg)
        except Exception as e:
            return {'code': 400, 'data': f'启用任务失败: {str(e)}'}
        scheduled_tasks[task_id] = job
        del paused_tasks[task_id]
        _save_tasks()
    log(f'▶️ 启用定时任务 → {task_id}')
    return {'code': 200, 'data': f'已启用任务: {task_id}'}


# 后台登录
_login_attempts = {}  # 客户端IP -> [失败次数, 最近失败时间]
_LOGIN_MAX_FAILS = 5       # 连续失败上限
_LOGIN_LOCK_WINDOW = 300   # 锁定时长（秒）= 5 分钟
login_attempts_lock = threading.Lock()


def _client_ip(request):
    """优先取 X-Forwarded-For（反代后真实客户端 IP），否则回退直连地址。"""
    if request is None:
        return '127.0.0.1'
    xff = (request.headers.get('x-forwarded-for') or '').split(',')[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else '127.0.0.1'


def _is_login_locked(ip):
    with login_attempts_lock:
        entry = _login_attempts.get(ip)
        if not entry:
            return False
        fails, last_ts = entry
        if time.time() - last_ts > _LOGIN_LOCK_WINDOW:
            _login_attempts.pop(ip, None)
            return False
        return fails >= _LOGIN_MAX_FAILS


def _record_login_fail(ip):
    with login_attempts_lock:
        now = time.time()
        entry = _login_attempts.get(ip)
        if not entry or (now - entry[1]) > _LOGIN_LOCK_WINDOW:
            _login_attempts[ip] = [1, now]
        else:
            entry[0] += 1
            entry[1] = now


@app.post('/Api/Login/Admin')
def admin_login(request: Request, payload: dict = Body(None)):
    global _last_login_ip
    body = payload or {}
    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    ip = _client_ip(request)

    if _is_login_locked(ip):
        return {'code': 429, 'data': f'登录失败次数过多，请 {_LOGIN_LOCK_WINDOW // 60} 分钟后再试'}

    if username == 'admin' and _verify_password(password, _password_hash):
        with login_attempts_lock:
            _login_attempts.pop(ip, None)
        _last_login_ip = ip
        token = generate_token()
        return {'code': 200, 'data': token}
    else:
        _record_login_fail(ip)
        return {'code': 400, 'data': '登录失败'}


@app.get('/Api/GetLastLoginIP')
def get_last_login_ip(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': _last_login_ip}


# 退出登录
@app.get('/Api/logout')
def logout(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    token = authorization[7:]
    remove_token(token)
    log('🚪 管理员已退出登录')
    return {'code': 200, 'data': '已退出登录'}


# 密码修改
@app.post('/Api/ChangePassword')
def change_password(payload: dict = Body(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    global _password_hash
    body = payload or {}
    old_password = str(body.get('old_password') or '')
    new_password = str(body.get('new_password') or '')
    if not _verify_password(old_password, _password_hash):
        return {'code': 400, 'data': '原密码错误'}
    if len(new_password) < 6:
        return {'code': 400, 'data': '新密码长度至少 6 位'}
    _password_hash = _hash_password(new_password)
    _config['password'] = _password_hash
    _save_config()  # 持久化到配置文件，后端/容器重启后仍生效
    # 修改密码后使所有已签发的 token 失效，强制重新登录
    with tokens_lock:
        _valid_tokens.clear()
    return {'code': 200, 'data': '密码修改成功，请重新登录'}


def _startup_restore():
    """进程启动即恢复定时任务并拉起调度线程。

    这样首页「定时任务」数量与「下次执行」在浏览器初始化前就是准确的；
    真正执行时若浏览器未就绪，_scheduled_send 会自动跳过并记录日志。
    """
    with tasks_lock:
        _restore_scheduled_tasks()
        _save_tasks()
    start_scheduler()  # 在 tasks_lock 之外调用，避免与 init_lock → tasks_lock 的加锁顺序相反


_startup_restore()


if __name__ == "__main__":
    host = os.environ.get('HOST', 'localhost')
    port = int(os.environ.get('PORT', '9844'))
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False
    )


