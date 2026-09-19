<template>
  <div class="page">
    <!-- 顶部操作栏 -->
    <div class="toolbar animate-fade-in-up">
      <el-button :icon="Refresh" @click="refreshAll" :loading="refreshing">刷新状态</el-button>
      <el-button
        v-if="!live"
        type="primary"
        :icon="VideoPlay"
        :loading="connecting"
        :disabled="!browserOk"
        @click="startStream"
      >
        连接画面
      </el-button>
      <el-button v-else type="danger" :icon="VideoPause" @click="stopStream">断开画面</el-button>
      <el-button :icon="Picture" @click="toggleFallback" :type="fallback ? 'warning' : ''">
        {{ fallback ? '关闭截图模式' : '截图模式（兜底）' }}
      </el-button>
      <a v-if="vncEnabled" class="vnc-entry" :href="vncUrl" target="_blank" rel="noopener">
        <el-icon><Monitor /></el-icon>
        打开 noVNC
      </a>
      <div class="toolbar__spacer"></div>
      <el-tag :type="loginStatus ? 'success' : 'info'" effect="light" round>
        <i class="dot" :class="loginStatus ? 'online' : 'offline'"></i>
        {{ loginStatus ? '已登录' : '未登录' }}
      </el-tag>
    </div>

    <el-row :gutter="16" class="wizard-row">
      <!-- 左：远程画面 -->
      <el-col :xs="24" :lg="15">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><el-icon><Monitor /></el-icon>远程画面</span>
            <span class="panel-head-right">
              <span class="panel-meta mono">
                {{ viewport.width || '—' }}×{{ viewport.height || '—' }}
                <template v-if="live"> · {{ fps }} fps · {{ frameKb }} KB/帧</template>
                <template v-else-if="fallback"> · 截图模式</template>
              </span>
              <el-button v-if="frameSrc" size="small" :icon="FullScreen" @click="fullscreen = !fullscreen">
                {{ fullscreen ? '收起' : '放大' }}
              </el-button>
            </span>
          </div>

          <div v-if="pageInfo.url" class="page-hint">
            <el-icon><Link /></el-icon>
            <span class="page-hint__title">{{ pageInfo.title || '当前页面' }}</span>
            <span class="page-hint__url mono">{{ shortUrl }}</span>
          </div>

          <div v-if="!browserOk" class="stream-empty">
            <el-empty description="浏览器尚未初始化">
              <el-button type="primary" @click="router.push('/home')">去首页初始化</el-button>
            </el-empty>
          </div>

          <div
            v-else
            class="screen-wrap"
            :class="{ grabbing: dragging, 'is-fullscreen': fullscreen }"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
            @pointerleave="onPointerUp"
            @wheel.prevent="onWheel"
            @contextmenu.prevent
          >
            <img
              v-if="frameSrc"
              :src="frameSrc"
              class="screen-img"
              alt="远程画面"
              @dblclick="fullscreen = !fullscreen"
            />
            <button v-if="fullscreen" class="screen-close" @click="fullscreen = false">收起画面</button>
            <div v-else class="screen-placeholder">
              <el-icon class="ph-icon"><Monitor /></el-icon>
              <p>{{ connecting ? '正在连接画面…' : '点击上方「连接画面」开始远程操作' }}</p>
              <p class="ph-tip">画面可直接点击操作：二次验证（接收手机验证码、扫码人脸识别）就在这里完成</p>
            </div>
          </div>

          <div class="screen-foot">
            <span class="foot-tip">
              <el-icon><InfoFilled /></el-icon>
              二次验证需在左侧画面里完成：接收手机验证码或扫码进行人脸识别
            </span>
            <span class="foot-status" :class="streamState">{{ streamText }}</span>
          </div>
        </div>
      </el-col>

      <!-- 右：步骤指引 -->
      <el-col :xs="24" :lg="9">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><el-icon><Key /></el-icon>登录步骤</span>
          </div>

          <ol class="stepper">
            <li
              v-for="(s, i) in stepList"
              :key="s.title"
              class="stepper__item"
              :class="{ 'is-done': activeStep > i, 'is-current': activeStep === i }"
            >
              <span class="stepper__dot">
                <el-icon v-if="activeStep > i"><Check /></el-icon>
                <template v-else>{{ i + 1 }}</template>
              </span>
              <div class="stepper__body">
                <div class="stepper__title">{{ s.title }}</div>
                <div class="stepper__desc">{{ s.desc }}</div>
              </div>
            </li>
          </ol>

          <div class="step-actions">
            <el-button
              type="primary"
              :icon="PictureFilled"
              :loading="qrLoading"
              :disabled="!browserOk || loginStatus"
              @click="loadQr"
            >
              获取登录二维码
            </el-button>
            <el-button :icon="RefreshRight" @click="loadQr" :disabled="!browserOk || loginStatus">
              刷新二维码
            </el-button>
          </div>

          <div v-if="qrImage && !loginStatus" class="qr-box">
            <img :src="qrImage" class="qr-img" alt="抖音登录二维码" />
            <span class="qr-tip">用抖音 App 扫一扫（有效期较短，过期请点刷新）</span>
          </div>

          <div v-if="loginStatus" class="done-box">
            <el-avatar :size="40" :src="douyinAvatar" :icon="UserFilled" />
            <div class="done-text">
              <div class="done-title">{{ douyinNickname || '已登录' }}</div>
              <div class="done-sub">抖音账号登录成功，可以回到首页使用了</div>
            </div>
            <el-button type="primary" @click="router.push('/home')">去首页</el-button>
          </div>

          <div class="divider"></div>

          <div class="kicker">短信验证码登录（可选）</div>
          <div class="sms-row">
            <el-input v-model="phone" placeholder="手机号" :disabled="loginStatus" />
            <el-button :loading="smsSending" :disabled="!browserOk || loginStatus" @click="sendSms">
              发送
            </el-button>
          </div>
          <div class="sms-row">
            <el-input v-model="smsCode" placeholder="验证码" maxlength="6" :disabled="loginStatus" />
            <el-button
              type="primary"
              :loading="smsSubmitting"
              :disabled="!browserOk || loginStatus"
              @click="submitSms"
            >
              提交
            </el-button>
          </div>

          <div class="divider"></div>

          <div class="kicker">在浏览器中填入文本</div>
          <div class="sms-row">
            <el-input v-model="inputText" placeholder="要填入当前输入框的文本" :disabled="!live" />
            <el-button :disabled="!live || !inputText" @click="sendText">填入</el-button>
          </div>
          <div class="key-row">
            <el-button size="small" :disabled="!live" @click="sendKey('Backspace')">退格</el-button>
            <el-button size="small" :disabled="!live" @click="sendKey('Tab')">Tab</el-button>
            <el-button size="small" type="primary" :disabled="!live" @click="sendKey('Enter')">
              回车
            </el-button>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  RefreshRight,
  VideoPlay,
  VideoPause,
  Picture,
  PictureFilled,
  Monitor,
  Key,
  InfoFilled,
  UserFilled,
  Link,
  FullScreen,
  Check
} from '@element-plus/icons-vue'
import {
  getScreenInfo,
  getScreenTicket,
  getScrlk,
  getLoginPng,
  getLoginStatus,
  getUserInfo,
  sendVerifyCode,
  submitVerifyCode
} from '../api/douyin'
import { NOVNC_URL } from '../config'
import { loginStatus, setLoginStatus, douyinAvatar, douyinNickname, setDouyinUser } from '../stores/browser'

const router = useRouter()
const vncUrl = NOVNC_URL

const browserOk = ref(false)
const vncEnabled = ref(true)
const refreshing = ref(false)
const viewport = reactive({ width: 0, height: 0 })
const pageInfo = reactive({ title: '', url: '' })
const shortUrl = computed(() => {
  const u = pageInfo.url || ''
  return u.replace(/^https?:\/\//, '').slice(0, 60)
})

// 画面
const live = ref(false)
const connecting = ref(false)
const fallback = ref(false)
const frameSrc = ref('')
const streamState = ref('idle')
const fps = ref(0)
const frameKb = ref(0)

// 步骤
const qrImage = ref('')
const qrLoading = ref(false)
const phone = ref('')
const smsCode = ref('')
const smsSending = ref(false)
const smsSubmitting = ref(false)
const inputText = ref('')
const fullscreen = ref(false)

const stepList = [
  { title: '扫码或验证码登录', desc: '生成二维码用抖音 App 扫一扫，也可用手机号验证码登录' },
  { title: '完成二次验证', desc: '按提示接收手机验证码或扫码人脸识别（在左侧画面里完成）' },
  { title: '确认登录状态', desc: '检测到已登录即完成，可回到首页使用定时任务' }
]

const activeStep = computed(() => (loginStatus.value ? 3 : qrImage.value ? 1 : 0))
const streamText = computed(() => ({
  idle: '未连接',
  connecting: '连接中…',
  live: '画面已连接',
  fallback: '截图模式（每秒刷新）',
  error: '连接失败'
}[streamState.value] || '未连接'))

let ws = null
let pollTimer = null
let fallbackTimer = null
let lastFrameAt = 0
let frameCount = 0
let objectUrl = ''
let dragging = false

// ---------- 状态 ----------
const refreshAll = async () => {
  refreshing.value = true
  try {
    const res = await getScreenInfo()
    const d = res.data || {}
    browserOk.value = !!d.browser
    vncEnabled.value = d.vnc_enabled !== false
    if (d.viewport) {
      viewport.width = d.viewport.width
      viewport.height = d.viewport.height
    }
    if (d.page) {
      pageInfo.title = d.page.title || ''
      pageInfo.url = d.page.url || ''
    }
  } catch (e) {
    browserOk.value = false
  }
  try {
    const res = await getLoginStatus()
    setLoginStatus(res.data === 'Yes')
  } catch (e) {}
  if (loginStatus.value) {
    await loadAccount()
  }
  refreshing.value = false
}

const loadAccount = async () => {
  if (!loginStatus.value) return
  try {
    const res = await getUserInfo()
    const d = res.data || {}
    setDouyinUser(d.nickname, d.avatar)
  } catch (e) {}
}

// ---------- 画面串流（CDP） ----------
const stopStream = (silent = false) => {
  if (ws) {
    try {
      ws.onclose = null
      ws.close()
    } catch (e) {}
    ws = null
  }
  live.value = false
  if (!fallback.value) streamState.value = 'idle'
  fps.value = 0
  frameKb.value = 0
  if (!silent && !fallback.value) ElMessage.info('已断开远程画面')
}

const startStream = async () => {
  if (live.value || connecting.value) return
  connecting.value = true
  streamState.value = 'connecting'
  try {
    const res = await getScreenTicket()
    const ticket = res.data && res.data.ticket
    if (!ticket) {
      streamState.value = 'error'
      return
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${window.location.host}/api/Api/Screen/Stream?ticket=${encodeURIComponent(ticket)}`)
    ws.binaryType = 'blob'
    ws.onmessage = onWsMessage
    ws.onclose = (ev) => {
      const wasLive = live.value
      stopStream(true)
      if (ev.code === 4401) {
        ElMessage.error('连接票据无效或已过期，请重新点击「连接画面」')
        streamState.value = 'error'
      } else if (ev.code === 4400 || ev.code === 4404) {
        ElMessage.error('浏览器未就绪，请先在首页初始化浏览器')
        streamState.value = 'error'
      } else if (wasLive) {
        ElMessage.warning('远程画面已断开（浏览器可能被重新初始化）')
        streamState.value = 'error'
      }
    }
    ws.onerror = () => {
      streamState.value = 'error'
    }
  } catch (e) {
    // 错误提示由响应拦截器统一处理（如"浏览器未初始化"）
    streamState.value = 'error'
  } finally {
    connecting.value = false
  }
}

const onWsMessage = (ev) => {
  if (typeof ev.data === 'string') {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.t === 'ready') {
        live.value = true
        streamState.value = 'live'
        if (msg.viewport) {
          viewport.width = msg.viewport.width
          viewport.height = msg.viewport.height
        }
        ElMessage.success('远程画面已连接')
      }
    } catch (e) {}
    return
  }
  // 二进制：一帧 JPEG
  const now = performance.now()
  frameCount += 1
  if (lastFrameAt) {
    const dt = (now - lastFrameAt) / 1000
    if (dt > 0) fps.value = Math.round(1 / dt)
  }
  lastFrameAt = now
  if (ev.data.size) frameKb.value = Math.round(ev.data.size / 1024)
  const url = URL.createObjectURL(ev.data)
  const old = objectUrl
  objectUrl = url
  frameSrc.value = url
  if (old) setTimeout(() => URL.revokeObjectURL(old), 1000)
  if (!live.value) {
    live.value = true
    streamState.value = 'live'
  }
}

// ---------- 截图兜底模式 ----------
const toggleFallback = () => {
  fallback.value = !fallback.value
  if (fallback.value) {
    stopStream(true)
    streamState.value = 'fallback'
    pullScreenshot()
    fallbackTimer = setInterval(pullScreenshot, 1000)
    ElMessage.info('已开启截图模式（每秒一张，CDP 不通时使用）')
  } else {
    if (fallbackTimer) {
      clearInterval(fallbackTimer)
      fallbackTimer = null
    }
    streamState.value = 'idle'
    frameSrc.value = ''
  }
}

const pullScreenshot = async () => {
  try {
    const res = await getScrlk()
    if (res.data) frameSrc.value = `data:image/png;base64,${res.data}`
  } catch (e) {}
}

// ---------- 输入转发 ----------
const send = (payload) => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload))
}

// 把屏幕坐标换算成浏览器视口内的 CSS 像素坐标。
// 关键：必须用 <img> 自身的矩形（而不是外层容器），否则全屏/留白时坐标会整体偏移；
// 帧尺寸优先取图片真实像素（naturalWidth/Height），保证缩放后仍然对齐。
const mapPoint = (ev) => {
  const wrap = ev.currentTarget
  const img = wrap.querySelector('.screen-img')
  const rect = (img || wrap).getBoundingClientRect()
  const fw = (img && img.naturalWidth) || viewport.width || rect.width
  const fh = (img && img.naturalHeight) || viewport.height || rect.height
  const clamp = (v, max) => Math.max(0, Math.min(max - 1, v))
  return {
    x: Math.round(clamp(((ev.clientX - rect.left) / rect.width) * fw, fw)),
    y: Math.round(clamp(((ev.clientY - rect.top) / rect.height) * fh, fh))
  }
}

// 触摸设备走 CDP 触摸事件，鼠标设备走鼠标事件
const isTouch = (ev) => ev.pointerType === 'touch'

const onPointerDown = (ev) => {
  if (!live.value) return
  const p = mapPoint(ev)
  dragging = true
  if (isTouch(ev)) send({ t: 'touch', a: 'start', ...p })
  else send({ t: 'mouse', a: 'down', b: 'left', ...p })
}

const onPointerMove = (ev) => {
  if (!live.value || !dragging) return
  const p = mapPoint(ev)
  if (isTouch(ev)) send({ t: 'touch', a: 'move', ...p })
  else send({ t: 'mouse', a: 'move', drag: 1, ...p })
}

const onPointerUp = (ev) => {
  if (!live.value || !dragging) return
  dragging = false
  const p = mapPoint(ev)
  if (isTouch(ev)) send({ t: 'touch', a: 'end', ...p })
  else send({ t: 'mouse', a: 'up', b: 'left', ...p })
}

const onWheel = (ev) => {
  if (!live.value) return
  const p = mapPoint(ev)
  send({ t: 'wheel', dy: ev.deltaY, ...p })
}

const sendText = () => {
  if (!inputText.value) return
  send({ t: 'text', text: inputText.value })
  ElMessage.success('已填入浏览器当前输入框')
}

const sendKey = (key) => send({ t: 'key', key })

// ---------- 登录流程 ----------
const loadQr = async () => {
  qrLoading.value = true
  try {
    const res = await getLoginPng()
    if (res.data) {
      qrImage.value = typeof res.data === 'string'
        ? (res.data.startsWith('data:') ? res.data : `data:image/png;base64,${res.data}`)
        : ''
      ElMessage.success('二维码已生成，请用抖音 App 扫码')
    }
  } catch (e) {
    // 拦截器已提示
  } finally {
    qrLoading.value = false
  }
}

const sendSms = async () => {
  if (!phone.value) return ElMessage.warning('请先填写手机号')
  smsSending.value = true
  try {
    await sendVerifyCode('86', phone.value)
    ElMessage.success('验证码已发送')
  } catch (e) {
  } finally {
    smsSending.value = false
  }
}

const submitSms = async () => {
  if (!smsCode.value) return ElMessage.warning('请填写验证码')
  smsSubmitting.value = true
  try {
    const res = await submitVerifyCode(smsCode.value)
    if (res.code === 200) ElMessage.success('提交成功，请留意画面中的后续验证')
    await pollLogin()
  } catch (e) {
  } finally {
    smsSubmitting.value = false
  }
}

const pollLogin = async () => {
  try {
    const res = await getLoginStatus()
    const ok = res.data === 'Yes'
    if (ok && !loginStatus.value) {
      setLoginStatus(true)
      await loadAccount()
      if (fallback.value) toggleFallback()
      if (live.value) stopStream(true)
      ElMessageBox.alert('抖音账号登录成功！可以回到首页使用定时任务了。', '登录完成', {
        confirmButtonText: '去首页'
      }).then(() => router.push('/home')).catch(() => {})
    } else if (!ok && loginStatus.value) {
      setLoginStatus(false)
    }
  } catch (e) {}
}

onMounted(async () => {
  await refreshAll()
  pollTimer = setInterval(pollLogin, 3000)
})

onUnmounted(() => {
  stopStream(true)
  if (pollTimer) clearInterval(pollTimer)
  if (fallbackTimer) clearInterval(fallbackTimer)
  if (objectUrl) URL.revokeObjectURL(objectUrl)
})
</script>

<style scoped>
.page {
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.vnc-entry {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--text-2);
  padding: 0 2px;
}

.vnc-entry:hover {
  color: var(--primary);
}

.toolbar .dot {
  margin-right: 6px;
}

.wizard-row {
  row-gap: 16px;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 18px;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-title .el-icon {
  color: var(--primary);
  font-size: 16px;
}

.panel-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-meta {
  font-size: 12px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.page-hint {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  padding: 7px 11px;
  background: var(--surface-muted);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--text-2);
  overflow: hidden;
}

.page-hint .el-icon {
  color: var(--text-3);
  flex-shrink: 0;
}

.page-hint__title {
  flex-shrink: 0;
  font-weight: 500;
}

.page-hint__url {
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---------- 画面 ---------- */
.screen-wrap {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  overflow: hidden;
  cursor: crosshair;
  touch-action: none;
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.screen-wrap.grabbing {
  cursor: grabbing;
}

/* 放大：手机上把画面铺满整屏，方便看清并操作 */
.screen-wrap.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 2200;
  border: none;
  border-radius: 0;
  background: #000;
}

.screen-wrap.is-fullscreen {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
}

/* 关键：图片盒子与显示区域一致（width/height 皆为 auto + 最大尺寸限制），
   这样 getBoundingClientRect 就是真实画面区域，触摸坐标才不会偏 */
.screen-wrap.is-fullscreen .screen-img {
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.screen-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 3;
  padding: 7px 14px;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: var(--radius-pill);
  cursor: pointer;
}

.screen-close:hover {
  background: rgba(0, 0, 0, 0.75);
}

.screen-img {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}

.screen-placeholder {
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
  padding: 40px 24px;
}

.screen-placeholder .ph-icon {
  font-size: 34px;
  color: var(--text-faint);
  margin-bottom: 8px;
}

.ph-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

.screen-empty {
  padding: 24px 0;
}

.screen-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.foot-tip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-3);
}

.foot-status {
  font-size: 12px;
  color: var(--text-3);
}

.foot-status.live {
  color: var(--success);
}

.foot-status.error {
  color: var(--danger);
}

.foot-status.connecting {
  color: var(--warning);
}

/* ---------- 步骤 ---------- */
/* ---------- 步骤条（引导线高度随内容自适应，不用 el-steps 的固定偏移） ---------- */
.stepper {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
}

.stepper__item {
  position: relative;
  display: flex;
  gap: 10px;
  padding-bottom: 14px;
}

.stepper__item:last-child {
  padding-bottom: 0;
}

/* 连接线：从圆点底部一直画到本项内容末尾（高度自动跟随文案换行） */
.stepper__item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 10px;
  top: 23px;
  bottom: 3px;
  width: 2px;
  border-radius: 2px;
  background: var(--border);
}

.stepper__item.is-done:not(:last-child)::before {
  background: color-mix(in srgb, var(--success) 55%, var(--border));
}

.stepper__dot {
  position: relative;
  z-index: 1;
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-3);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  font-variant-numeric: tabular-nums;
}

.stepper__dot .el-icon {
  font-size: 12px;
}

.stepper__item.is-current .stepper__dot {
  color: #fff;
  background: var(--primary);
  border-color: var(--primary);
}

.stepper__item.is-done .stepper__dot {
  color: #fff;
  background: var(--success);
  border-color: var(--success);
}

.stepper__body {
  min-width: 0;
}

.stepper__title {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-1);
}

.stepper__item.is-current .stepper__title {
  color: var(--primary);
}

.stepper__desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-3);
}

.step-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.qr-box {
  margin-top: 12px;
  padding: 14px;
  background: var(--surface-muted);
  border-radius: var(--radius-md);
  text-align: center;
}

.qr-img {
  width: 180px;
  height: 180px;
  border-radius: var(--radius-sm);
  background: #fff;
}

.qr-tip {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-3);
}

.done-box {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding: 12px 14px;
  border: 1.5px solid var(--success);
  background: color-mix(in srgb, var(--success) 7%, var(--surface));
  border-radius: var(--radius-md);
}

.done-text {
  flex: 1;
  min-width: 0;
}

.done-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-1);
}

.done-sub {
  font-size: 12px;
  color: var(--text-3);
}

.divider {
  height: 1px;
  background: var(--border);
  margin: 16px 0 12px;
}

.kicker {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--primary);
  margin-bottom: 8px;
}

.sms-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.key-row {
  display: flex;
  gap: 8px;
}

/* ---------- 手机端 ---------- */
@media (max-width: 768px) {
  .toolbar .el-button {
    flex: 1 1 auto;
    margin-left: 0;
  }

  .panel {
    padding: 14px;
  }

  .screen-wrap {
    min-height: 42vh;
  }

  .panel-head-right {
    gap: 6px;
  }

  .panel-meta {
    font-size: 11px;
  }

  .qr-img {
    width: 160px;
    height: 160px;
  }

  .sms-row {
    flex-wrap: wrap;
  }

  .sms-row .el-input {
    flex: 1 1 150px;
  }
}
</style>
