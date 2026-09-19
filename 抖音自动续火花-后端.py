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


def _chromium_using_profile(profile_dir: str) -> bool:
    """是否有 Chromium 进程正在使用指定资料目录。"""
    try:
        out = subprocess.run(['pgrep', '-f', f'--user-data-dir={profile_dir}'],
                             capture_output=True, text=True, timeout=5)
        return bool((out.stdout or '').strip())
    except Exception:
        return False


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
    # 长期运行：限制磁盘缓存，避免数据卷里的资料目录无限增长（写满磁盘会导致容器起不来）
    opts.add_argument('--disk-cache-size=67108864')  # 64MB
    # 保存登录数据（Cookie）：开启时使用持久化 user-data-dir，浏览器重启后仍保持抖音登录
    if _config.get('save_session'):
        try:
            profile_dir = os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE)), 'chrome-profile')
            os.makedirs(profile_dir, exist_ok=True)
            # 只有当没有 Chromium 正在使用该资料目录时才清锁：
            # 若旧实例还活着就删锁，会让两个 Chromium 共用同一 profile → 资料损坏、登录态丢失
            if _chromium_using_profile(profile_dir):
                log('⚠️ 检测到仍有 Chromium 在使用登录资料目录，跳过锁清理（避免损坏资料）')
            else:
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

    # 会话列表里"名字/头像/火花"的稳定选择器（对应抖音聊天页 DOM）
    _FRIEND_TITLE_SEL = '[class*="conversationConversationItemtitle"]'
    _FRIEND_AVATAR_SEL = 'img[src*="douyinpic.com"]'
    _FRIEND_STREAK_SEL = '[class*="commonStreaknormalText"]'

    # 一次 JS 调用把整屏会话解析成 [{name, avatar, fire}]：
    # 以"名字元素"为锚点就地向上找整行，再在行内取头像/火花，避免用序号拼 xpath
    # （列表虚拟滚动且按最近消息动态排序，序号会串到别人）。
    _EXTRACT_FRIENDS_JS = """
        const w = arguments[0];
        const titles = [...w.querySelectorAll('%(title)s')].filter(e => !/Wrapper/.test(e.className));
        const rows = [];
        for (const t of titles) {
          const name = (t.innerText || '').trim().split('\n')[0].trim();
          if (!name) continue;
          // 以名字元素为锚点向上找"整行"：最多爬 4 层，且该祖先内必须只有一个名字元素
          // （否则说明已经爬到列表容器，会取到别人的头像/火花 → 宁可留空也不能取错人）
          let row = null;
          let node = t;
          for (let i = 0; i < 4 && node.parentElement; i++) {
            node = node.parentElement;
            const cnt = [...node.querySelectorAll('%(title)s')].filter(e => !/Wrapper/.test(e.className)).length;
            if (cnt === 1 && node.querySelector('%(avatar)s')) { row = node; break; }
          }
          const img = row ? row.querySelector('%(avatar)s') : null;
          const st = row ? row.querySelector('%(streak)s') : null;
          rows.push({
            name: name,
            avatar: img ? (img.getAttribute('src') || '') : '',
            fire: st ? (st.innerText || '').trim() : ''
          });
        }
        return JSON.stringify(rows);
    """ % {'title': _FRIEND_TITLE_SEL, 'avatar': _FRIEND_AVATAR_SEL, 'streak': _FRIEND_STREAK_SEL}

    def Updara_FrinderList(self):
        """读取会话列表里的全部好友（名字 / 头像 / 火花天数）。

        三个关键点：
          1. 会话列表是**虚拟滚动**的：必须边滚边抓，并且**跨轮累积**结果
             （只保留最后一轮的话，拿到的是列表末端那一屏，前面的好友会全部丢失）；
          2. 列表按最近消息**动态排序**：按"名字元素"锚点就地取头像/火花，不用序号 xpath；
          3. 失败与"确实没有好友"要能区分：页面未就绪/脚本异常返回 None，真的为空返回 []。
        """
        with driver_lock:
            wrapper_xpath = '//div[@class="conversationConversationListwrapper"]'
            wrapper_el = None
            for attempt in range(3):
                try:
                    wrapper_el = driver.find_element(By.XPATH, wrapper_xpath)
                    break
                except Exception:
                    if attempt == 0:
                        time.sleep(1.5)          # 首次可能只是页面还在加载
                    else:
                        try:
                            _recover_douyin_page('读取好友列表时页面未就绪')
                        except Exception:
                            pass
                        time.sleep(1.5)
            if wrapper_el is None:
                log('⚠️ 读取好友列表失败：聊天页未就绪（已尝试等待并恢复页面）')
                return None

            scroll_js = (
                'const w = arguments[0]; let moved = false;'
                'const all = [w].concat([...w.querySelectorAll("*")]);'
                'for (const e of all) {'
                '  if (e.scrollHeight > e.clientHeight + 2) {'
                '    const before = e.scrollTop; e.scrollTop = e.scrollHeight;'
                '    if (e.scrollTop !== before) moved = true;'
                '  }'
                '}'
                'return moved;'
            )

            def grab():
                try:
                    return json.loads(driver.execute_script(self._EXTRACT_FRIENDS_JS, wrapper_el) or '[]')
                except Exception as e:
                    log(f'⚠️ 解析会话列表失败：{e}')
                    return None

            merged = {}
            script_fail = 0
            for _ in range(40):
                batch = grab()
                if batch is None:
                    script_fail += 1
                    if script_fail >= 3:
                        break
                    time.sleep(0.5)
                    continue
                script_fail = 0
                for item in batch:
                    name = (item.get('name') or '').strip()
                    if name and name not in merged:
                        merged[name] = item
                try:
                    moved = driver.execute_script(scroll_js, wrapper_el)
                except Exception:
                    moved = False
                if not moved:
                    # 滚不动了：再抓一轮（可能刚好有新加载的项）后结束
                    time.sleep(0.6)
                    tail = grab()
                    if tail:
                        for item in tail:
                            name = (item.get('name') or '').strip()
                            if name and name not in merged:
                                merged[name] = item
                    break
                time.sleep(0.4)

            if not merged:
                if script_fail:
                    log('⚠️ 读取好友列表失败：解析会话列表连续异常（页面结构可能已变化）')
                    return None
                log('ℹ️ 会话列表为空（该账号当前没有会话）')
                return []

            temp_list = []
            self.friends_xpath_list.clear()
            for name, item in merged.items():
                temp_list.append(UserFriendsInfo(name, item.get('avatar') or '', item.get('fire') or ''))
            self._friends_cache_time = time.time()
            return temp_list

    # ---------- 发送消息用的辅助判断（都是页面级轻量查询） ----------
    def _current_chat_title(self):
        """右侧当前打开会话的好友名；没有打开任何会话时返回空串。

        注意：该标题元素的文本常带火花状态（如 "余佳扬\n重燃中 1/3"），只取第一行做比对。
        """
        try:
            el = driver.find_element(By.XPATH, '//*[contains(@class,"RightPanelHeadertitle")]')
            text = (el.text or '').strip()
            return text.splitlines()[0].strip() if text else ''
        except Exception:
            return ''

    def _my_message_count(self):
        """当前会话里"我发出的消息"条数；查询失败返回 None（不能当成 0，否则会把"历史加载"误判为新消息）。"""
        try:
            return len(driver.find_elements(By.XPATH, '//*[contains(@class,"messageMessageBoxisFromMe")]'))
        except Exception:
            return None

    def _last_my_bubble_text(self):
        """最后一条"我发出的消息"的文本（用来确认本条消息真的进了会话）。"""
        try:
            els = driver.find_elements(By.XPATH, '//*[contains(@class,"messageMessageBoxisFromMe")]')
            for el in reversed(els):
                txt = (el.text or '').strip()
                if txt:
                    return txt
        except Exception:
            pass
        return ''

    def _wait_message_list_stable(self, timeout=6.0):
        """等消息区加载稳定（连续两次采样条数一致），避免把"历史消息异步渲染"当成新消息。"""
        deadline = time.time() + timeout
        prev = self._my_message_count()
        same = 0
        while time.time() < deadline:
            time.sleep(0.4)
            cur = self._my_message_count()
            if cur is not None and cur == prev:
                same += 1
                if same >= 2:
                    return cur
            else:
                same = 0
            prev = cur
        return prev

    def _wait_message_sent(self, before_count, text, timeout=6.0):
        """确认消息真的进了会话：以"最后一条自己的消息内容 == 本条内容"为主，数量增加为辅。

        历史问题：老实现发完回车直接返回成功；后来改成"条数增加即成功"也不够严谨——
        新会话的历史消息是异步渲染的，回车后即使没发出去，历史气泡也会让条数从 0 涨上去。
        因此这里先用 _wait_message_list_stable 拿到稳定基线，再以文本匹配为准。
        """
        target = (text or '').strip()
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.4)
            if target and self._last_my_bubble_text() == target:
                return True
            cur = self._my_message_count()
            if target == '' and cur is not None and before_count is not None and cur > before_count:
                return True   # 空文本消息只能靠条数判断
        return False

    def _find_friend_element(self, name):
        """按名字在会话列表里实时查找好友行（列表虚拟化 + 按最近消息动态排序，不能用旧序号 xpath）。

        返回可点击的元素；找不到返回 None。
        """
        if not name or '"' in name:
            return None
        wrapper_xpath = '//div[@class="conversationConversationListwrapper"]'
        title_xpath = ('.//*[contains(@class,"conversationConversationItemtitle")'
                       ' and normalize-space(text())="%s"]' % name)
        try:
            wrapper = driver.find_element(By.XPATH, wrapper_xpath)
        except Exception:
            return None
        try:
            return wrapper.find_element(By.XPATH, title_xpath)
        except Exception:
            pass
        # 没在当前视口内：滚到顶部后逐屏滚动查找（最多 12 屏）
        try:
            driver.execute_script("arguments[0].scrollTop = 0;", wrapper)
            time.sleep(0.3)
            for _ in range(12):
                try:
                    return wrapper.find_element(By.XPATH, title_xpath)
                except Exception:
                    pass
                moved = driver.execute_script(
                    "const w = arguments[0]; const before = w.scrollTop;"
                    "w.scrollTop = before + w.clientHeight - 40;"
                    "return w.scrollTop !== before;", wrapper)
                if not moved:
                    break
                time.sleep(0.4)
        except Exception:
            pass
        return None

    def _click_friend(self, name):
        """点击目标好友的会话行；点击前按名字定位，避免列表重排后点到别人。"""
        el = self._find_friend_element(name)
        if el is None:
            return False, '会话列表里没有找到该好友'
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
        except Exception:
            pass
        try:
            row = el.find_element(By.XPATH, 'ancestor::*[contains(@class,"conversationConversationItem")][1]')
            row.click()
        except Exception:
            el.click()
        return True, ''

    def Send_Frinder(self, name: str, text: str):
        with driver_lock:
            try:
                count = self.Updara_FrinderList()
            except Exception as e:
                return TrueString(False, e)
            if not count:
                print("⚠️ 更新好友列表失败!")
                return TrueString(False, '未获取到好友列表（页面未就绪或未登录）')

            last_error = ''
            # 最多尝试两次：首次失败（常见于聊天区为空 / 会话未切换成功）自动重试一次
            for attempt in (1, 2):
                try:
                    ok, err = self._click_friend(name)
                    if not ok:
                        last_error = err
                        continue

                    # ① 确认右侧真的切到了这位好友，否则会把消息发给别人
                    opened = ''
                    for _ in range(12):
                        time.sleep(0.4)
                        opened = self._current_chat_title()
                        # 严格相等（去空白）：绝不能用子串包含判断，
                        # 否则"A 是 B 名字子串"时会往别人的会话里发消息还报成功
                        if _norm_name(opened) == _norm_name(name):
                            break
                    if _norm_name(opened) != _norm_name(name):
                        last_error = f'会话未切换成功（当前打开：{opened or "无"}）'
                        continue

                    # ② 输入并发送（先聚焦输入框，避免聊天区为空时输入落空）
                    # 先等消息区加载稳定再取基线（否则会把"历史消息加载"误判成本次发送成功）
                    before = self._wait_message_list_stable()
                    if before is None:
                        before = self._my_message_count()
                    seng = driver.find_element(
                        By.XPATH, value='//div[@class="messageEditorimChatEditorContainer"]/div/div')
                    seng.click()
                    time.sleep(0.2)
                    seng.send_keys(text)
                    time.sleep(0.2)
                    seng.send_keys(Keys.ENTER)

                    # ③ 校验消息确实出现在会话里，否则视为失败（不再误报成功）
                    if self._wait_message_sent(before, text, timeout=5.0):
                        return TrueString(True, None)
                    last_error = '消息未出现在会话中（发送未生效）'
                except Exception as e:
                    last_error = str(e)
            return TrueString(False, last_error or '发送失败')

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
# 默认关闭 Swagger/OpenAPI（它们经 nginx 是匿名可达的，会泄露全部接口清单）；
# 需要调试时用环境变量 ENABLE_DOCS=1 打开。
_DOCS_ENABLED = os.environ.get('ENABLE_DOCS', '0').strip().lower() in ('1', 'true', 'yes', 'on')
app = FastAPI(
    docs_url='/docs' if _DOCS_ENABLED else None,
    redoc_url='/redoc' if _DOCS_ENABLED else None,
    openapi_url='/openapi.json' if _DOCS_ENABLED else None,
)

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


def _atomic_write_json(path, data):
    """原子写 JSON：临时文件 + fsync + os.replace。

    直接 open(path,'w') 在写入过程中被 kill/OOM/磁盘写满时会留下半截文件，
    下次启动解析失败 → 任务/密码被当成"空"处理，进而被空内容覆盖（数据永久丢失）。
    """
    tmp = f'{path}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f'⚠️ 原子写失败 {path}: {e}')
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _quarantine_corrupt_file(path):
    """把损坏的持久化文件改名保留（便于人工恢复），返回新路径。"""
    try:
        bad = f'{path}.corrupt-{datetime.now().strftime("%Y%m%d%H%M%S")}'
        os.replace(path, bad)
        return bad
    except Exception:
        return None


def _save_config():
    """把当前配置（含密码哈希）原子写回配置文件。"""
    with config_lock:
        if _config_load_failed:
            print('⚠️ 配置此前读取失败，出于安全考虑拒绝写回（避免覆盖原文件）')
            return
        if not _atomic_write_json(CONFIG_FILE, dict(_config)):
            print('⚠️ 配置持久化失败')


def _load_config():
    """启动时加载配置。

    安全要求：**配置文件损坏时绝不自动重置为默认口令**（老实现会静默把管理员密码改回
    admin/123456 并落盘，等于把后台交出去）。损坏时保留原文件并禁用写回，只允许用
    环境变量 ADMIN_PASSWORD 重置。
    """
    global _password_hash, _config_load_failed
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            _config_load_failed = True
            bad = _quarantine_corrupt_file(CONFIG_FILE)
            print(f'⚠️ 配置文件损坏（已保留为 {bad}）：{e}')
            env_pwd = os.environ.get('ADMIN_PASSWORD', '')
            if env_pwd:
                _password_hash = _hash_password(env_pwd)
                _config.clear()
                _config['password'] = _password_hash
                _config['save_session'] = False
                print('✅ 已按环境变量 ADMIN_PASSWORD 重置管理员密码')
                return
            print('❌ 无法确定管理员密码：请修复配置后重启，或设置环境变量 ADMIN_PASSWORD 重置密码')
            _password_hash = _hash_password(secrets.token_urlsafe(24))  # 随机口令，避免出现默认口令
            _config.clear()
            _config['password'] = _password_hash
            _config['save_session'] = False
            return
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
    """校验浏览器是否已初始化**且仍然可用**，否则返回友好提示。"""
    if not init:
        return {'code': 400, 'data': '浏览器未初始化，请先在首页初始化浏览器'}
    if not _driver_alive():
        return {'code': 400, 'data': '浏览器会话已失效，请点击「重新初始化浏览器」恢复'}
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
    """将当前定时任务（含已停用）原子写回 JSON 文件；须在 tasks_lock 内调用。"""
    if _tasks_load_failed:
        print('⚠️ 任务文件此前读取失败，出于保护拒绝写回（避免用空列表覆盖原文件）')
        return
    data = {
        'scheduled': {task_id: _job_to_meta(job) for task_id, job in scheduled_tasks.items()},
        'paused': dict(paused_tasks),
        # 未注册成功的待恢复任务也要落盘，否则会被静默丢弃
        'pending': dict(_pending_tasks),
    }
    if not _atomic_write_json(TASKS_FILE, data):
        print('⚠️ 任务持久化失败')


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
        _tasks_load_failed = True
        bad = _quarantine_corrupt_file(TASKS_FILE)
        print(f'⚠️ 任务文件损坏（已保留为 {bad}），本次不覆盖磁盘文件：{e}')


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
def _scheduled_send(name, text, _retried=False):
    """定时任务执行入口：调用发送并输出执行结果日志（供 schedule 调度）。

    入参保持 (name, text) 形态，与任务持久化/编辑解析逻辑一致；
    _retried 标记用于"顺延重试一次"，避免无限重试。
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
@app.get('/healthz')  # 健康检查（免鉴权）：仅返回各组件是否存活，不泄露敏感信息
def healthz():
    browser_ok = bool(init) and _driver_alive()
    return {
        'backend': 'Yes',
        'browser': 'Yes' if browser_ok else 'No',
        'scheduler': 'Yes' if _scheduler_alive() else 'No',
    }


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
        globals()['_self_avatar_cache'] = ''   # 登录态变化时清缓存，避免串到上一个账号
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
        # 兜底：quit() 失败/僵死时可能有 Chromium 仍在跑，继续用同一资料目录会损坏登录态
        profile_dir = os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE)), 'chrome-profile')
        if _chromium_using_profile(profile_dir):
            log('🧹 检测到残留的 Chromium 仍占用资料目录，正在结束它们…')
            try:
                subprocess.run(['pkill', '-f', f'--user-data-dir={profile_dir}'], timeout=8, capture_output=True)
            except Exception:
                pass
            for _ in range(10):
                if not _chromium_using_profile(profile_dir):
                    break
                time.sleep(0.5)


def _create_browser_locked():
    """创建浏览器会话（调用方必须已持有 init_lock，RLock 可重入）。

    供 /Api/Init（首次初始化）与 /Api/ReInit（重新初始化）复用。
    """
    global init, driver, douyin, options

    try:
        options = unban_config()  # 每次新建，重试初始化不会叠加重复参数
        new_driver = webdriver.Chrome(service=service, options=options) if service else webdriver.Chrome(options=options)
        try:
            # 关键：给 WebDriver 命令加超时。页面卡死时若无超时，调用会永久阻塞，
            # 而调用方持有 driver_lock，会把所有 API 线程一起拖死（连登录接口都打不开）
            try:
                new_driver.set_page_load_timeout(45)
                new_driver.set_script_timeout(20)
            except Exception:
                pass
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
        if not cookie_data:
            return {'code': 404, 'data': 'Cookie 内容为空，请重新导出后再试'}
        with driver_lock:
            # 先清空旧 Cookie：避免"半套新 Cookie + 旧 Cookie"混用导致状态不明
            try:
                driver.delete_all_cookies()
            except Exception:
                pass
            failed = []
            for cookie in cookie_data:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    failed.append(str(e)[:40])
            if failed:
                log(f'⚠️ 导入 Cookie 有 {len(failed)}/{len(cookie_data)} 条失败：{failed[:3]}')
                if len(failed) == len(cookie_data):
                    return {'code': 404, 'data': 'Cookie 导入失败（域名/格式不匹配），请重新导出'}
            # 回到聊天页并**正向等待**登录后才存在的标志，避免"没看到登录面板"就判成功
            try:
                driver.get(DOUYIN_CHAT_URL)
            except Exception:
                pass
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    driver.find_element(By.XPATH, '//div[@class="conversationConversationListwrapper"]')
                    Login_is_bool = True
                    log('🔑 登录状态变更：Cookie 登录成功')
                    return {'code': 200, 'data': 'ok'}
                except NoSuchElementException:
                    time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)
            Login_is_bool = False
            return {'code': 404, 'data': 'login-error-cooker cant login（Cookie 可能已失效）'}
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
        if friends_list is None:
            # 页面未就绪 / 解析异常：明确报错，避免和"真的没有好友"混淆（老实现都返回 200 空列表）
            return {'code': 404, 'data': '读取好友列表失败：聊天页未就绪或页面结构已变化，请稍后重试'}
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
    # 不再做"扫描页面头像 img"的兜底：聊天页里最后一张头像往往是**好友**的头像，
    # 会被误当成自己的头像返回。取不到就返回空，宁可不显示也不要显示错的。
    # ② 最后返回缓存（缓存只可能来自上面准确的 JSON 路径）
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
        if active:
            # 新建会话时刷新输入时间，避免刚连上就被判定为"闲置"
            global _last_remote_input_at
            _last_remote_input_at = time.time()


def remote_session_open():
    """是否有远程画面会话正在连着（严格：用于单会话互斥）。"""
    with _remote_control_lock:
        return bool(_remote_control_active)


# 远程会话空闲多久后视为结束：避免"标签页挂着没操作"导致定时任务全天被跳过
_REMOTE_IDLE_SECONDS = 180


def remote_control_active():
    """是否有人**正在**远程操作浏览器（以最近真实输入为准，且有闲置过期）。

    老实现只看"有没有 WebSocket 连接"，标签页挂着就一直算占用，当晚的定时任务会被
    静默跳过且不再重试（用户第二天才发现火花断了）。
    """
    with _remote_control_lock:
        if not _remote_control_active:
            return False
        return (time.time() - _last_remote_input_at) < _REMOTE_IDLE_SECONDS


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
    activated = False
    try:
        # 必须先把浏览器窗口激活，否则 Esc 落到别的窗口上不起作用
        r = subprocess.run(['xdotool', 'search', '--name', 'douyin',
                            'windowactivate', '--sync'],
                           timeout=5, capture_output=True)
        activated = (r.returncode == 0)
    except Exception:
        activated = False
    try:
        r = subprocess.run(['xdotool', 'key', '--clearmodifiers', 'Escape'],
                           timeout=5, capture_output=True)
        ok = (r.returncode == 0)
    except Exception:
        ok = False
    # 只有真正成功才记成功日志：老实现无条件打印"已清理"，openbox 挂掉时会掩盖真实故障
    if reason and ok and activated:
        log(f'🧹 已清理浏览器模态弹窗（{reason}）')
    elif reason and not activated:
        log(f'⚠️ 未能激活浏览器窗口（openbox 可能已退出），弹窗清理可能失效（{reason}）')


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
    if remote_session_open():
        return {'code': 409, 'data': '已有其它页面正在远程连接浏览器，请先关闭那个页面'}
    return {'code': 200, 'data': {'ticket': _issue_screen_ticket(), 'expires_in': _SCREEN_TICKET_TTL}}


@app.websocket('/Api/Screen/Stream')  # 远程画面：CDP 画面串流 + 输入转发
async def ScreenStream(websocket: WebSocket):
    if not _consume_screen_ticket(websocket.query_params.get('ticket') or ''):
        await websocket.close(code=4401)  # 票据无效 / 过期 / 已使用
        return
    if websockets is None or not (init and _driver_alive()):
        await websocket.close(code=4400)
        return
    # 空窗防护：签发票据与真正建连之间可能被另一个页面插队，这里再判一次
    if remote_session_open():
        await websocket.close(code=4409)
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
    """取真实客户端 IP。

    安全要点：**只信任 X-Forwarded-For 的最后一段**。nginx 用
    `$proxy_add_x_forwarded_for` 会把客户端自带的 XFF 放在前面、真实地址追加在最后；
    老实现取第一段，攻击者每个请求换一个伪造 XFF 就能让"5 次失败锁定"完全失效。
    """
    if request is None:
        return '127.0.0.1'
    xff = (request.headers.get('x-forwarded-for') or '').strip()
    if xff:
        parts = [p.strip() for p in xff.split(',') if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else '127.0.0.1'


def _is_login_locked(ip):
    with login_attempts_lock:
        now = time.time()
        # 顺带清理过期条目：防止伪造 IP 让字典无限增长（长期运行的内存泄漏）
        for key in [k for k, v in list(_login_attempts.items())
                    if now - (v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else 0) > _LOGIN_LOCK_WINDOW]:
            _login_attempts.pop(key, None)
        entry = _login_attempts.get(ip)
        if not entry:
            return False
        fails, last_ts = entry
        if now - last_ts > _LOGIN_LOCK_WINDOW:
            _login_attempts.pop(ip, None)
            return False
        if fails >= _LOGIN_MAX_FAILS:
            return True
        # 全局兜底：与 IP 无关的总失败量过高也锁一段时间，抵御分布式/伪造 IP 的爆破
        total = sum(int(v[0] or 0) for v in _login_attempts.values() if isinstance(v, (list, tuple)))
        return total >= _LOGIN_MAX_FAILS * 6


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


def _auto_init_browser():
    """启动后自动初始化浏览器（默认开启，AUTO_INIT_BROWSER=0 可关闭）。

    没有这一步时：每次容器重启/宿主机重启后，浏览器都不会被创建，
    定时任务到点只会静默跳过（"⏭️ 浏览器未初始化"），用户往往几天后才发现火花断了。
    """
    if os.environ.get('AUTO_INIT_BROWSER', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        log('ℹ️ AUTO_INIT_BROWSER=0，跳过启动自动初始化浏览器')
        return
    for attempt in range(1, 6):
        time.sleep(3 if attempt == 1 else min(60, 8 * attempt))
        if init and _driver_alive():
            return
        try:
            with init_lock:
                if init and _driver_alive():
                    return
                if init:
                    _reset_driver_state()
                res = _create_browser_locked()
            if (res or {}).get('code') == 200:
                log('🚀 启动自动初始化浏览器成功')
                return
            log(f'⚠️ 启动自动初始化浏览器未成功（第 {attempt} 次）：{res}')
        except Exception as e:
            log(f'⚠️ 启动自动初始化浏览器异常（第 {attempt} 次）：{e}')
    log('⚠️ 自动初始化浏览器多次失败，请到首页手动点击「初始化浏览器」')


def _browser_watchdog():
    """浏览器看门狗：周期性探测浏览器，崩溃/会话失效时自动重建（BROWSER_WATCHDOG=0 可关闭）。

    同时顺带清理可能出现的模态弹窗（用户最近有输入时不打扰）。
    """
    if os.environ.get('BROWSER_WATCHDOG', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        return
    while True:
        time.sleep(60)
        try:
            if not init:
                continue
            if _driver_alive():
                if not _remote_input_recent(10):
                    _dismiss_browser_dialogs()
                continue
            log('🩺 看门狗发现浏览器已失效，尝试自动重建…')
            with init_lock:
                if driver and not _driver_alive():
                    _reset_driver_state()
                if not init:
                    res = _create_browser_locked()
                    log(f'🩺 自动重建结果：{res}')
        except Exception as e:
            log(f'⚠️ 看门狗异常：{e}')


_startup_restore()
threading.Thread(target=_auto_init_browser, daemon=True, name='auto-init-browser').start()
threading.Thread(target=_browser_watchdog, daemon=True, name='browser-watchdog').start()


if __name__ == "__main__":
    host = os.environ.get('HOST', 'localhost')
    port = int(os.environ.get('PORT', '9844'))
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False
    )


