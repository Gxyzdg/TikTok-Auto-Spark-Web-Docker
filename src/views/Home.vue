<template>
  <div class="page">
    <!-- 欢迎横幅 -->
    <section class="hero">
      <div class="hero-inner">
        <div class="hero-text">
          <h1 class="hero-title">欢迎使用抖音火花助手</h1>
          <p class="hero-subtitle">自动化管理你的抖音好友火花，保持联系不间断</p>
        </div>
        <div class="hero-actions">
          <el-tag
            :type="browserStatus && loginStatus ? 'success' : 'warning'"
            effect="light"
            round
            class="hero-tag"
          >
            {{ browserStatus && loginStatus ? '系统运行正常' : '待初始化' }}
          </el-tag>
          <el-button :icon="Refresh" round @click="refreshAll" :loading="refreshing">
            刷新
          </el-button>
        </div>
      </div>
    </section>

    <!-- 状态卡片 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon browser"><el-icon><Monitor /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">浏览器状态</span>
            <span class="stat-value">
              <i class="dot" :class="browserStatus ? 'online' : 'offline'"></i>
              {{ browserStatus ? '已初始化' : '未初始化' }}
            </span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon login"><el-icon><Key /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">登录状态</span>
            <span class="stat-value">
              <i class="dot" :class="loginStatus ? 'online' : 'offline'"></i>
              {{ loginStatus ? '已登录' : '未登录' }}
            </span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon friends"><el-icon><User /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">好友数量</span>
            <span class="stat-value number">{{ friendsDisplay }} <em>人</em></span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon tasks"><el-icon><Clock /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">定时任务</span>
            <span class="stat-value number">{{ tasksDisplay }} <em>个</em></span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 快速操作 + 系统信息 -->
    <el-row :gutter="20" class="main-row">
      <el-col :xs="24" :lg="14">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><el-icon><Operation /></el-icon>快速操作</span>
          </div>
          <div class="action-grid">
            <div
              class="action-item"
              :class="{ loading: initLoading }"
              tabindex="0"
              role="button"
              @click="initBrowser"
              @keydown.enter="onActionKeydown"
              @keydown.space.prevent="onActionKeydown"
            >
              <div class="action-icon browser"><el-icon><Monitor /></el-icon></div>
              <div class="action-text">
                <span class="action-name">初始化浏览器</span>
                <span class="action-hint">启动自动化环境</span>
              </div>
            </div>
            <div
              class="action-item"
              tabindex="0"
              role="button"
              @click="refreshFriends"
              @keydown.enter="onActionKeydown"
              @keydown.space.prevent="onActionKeydown"
            >
              <div class="action-icon refresh"><el-icon><Refresh /></el-icon></div>
              <div class="action-text">
                <span class="action-name">刷新好友列表</span>
                <span class="action-hint">更新好友数据</span>
              </div>
            </div>
            <div
              class="action-item"
              tabindex="0"
              role="button"
              @click="router.push('/tasks')"
              @keydown.enter="onActionKeydown"
              @keydown.space.prevent="onActionKeydown"
            >
              <div class="action-icon tasks"><el-icon><Clock /></el-icon></div>
              <div class="action-text">
                <span class="action-name">管理定时任务</span>
                <span class="action-hint">添加或修改任务</span>
              </div>
            </div>
            <div
              class="action-item"
              tabindex="0"
              role="button"
              @click="router.push('/settings')"
              @keydown.enter="onActionKeydown"
              @keydown.space.prevent="onActionKeydown"
            >
              <div class="action-icon settings"><el-icon><Setting /></el-icon></div>
              <div class="action-text">
                <span class="action-name">系统设置</span>
                <span class="action-hint">配置账户信息</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :lg="10">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><el-icon><InfoFilled /></el-icon>系统信息</span>
          </div>
          <div class="info-list">
            <div class="info-item">
              <span class="info-label">系统版本</span>
              <span class="info-value">{{ APP_VERSION }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">项目已运行</span>
              <span class="info-value uptime">{{ uptime }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">API 地址</span>
              <span class="info-value">{{ API_HOST }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">前端端口</span>
              <span class="info-value">{{ FRONTEND_PORT }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">VNC 端口</span>
              <span class="info-value">
                <a :href="vncUrl" target="_blank" class="vnc-link">
                  进入 noVNC (6080) <el-icon><TopRight /></el-icon>
                </a>
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">运行状态</span>
              <el-tag
                :type="browserStatus && loginStatus ? 'success' : 'warning'"
                size="small"
                effect="light"
              >
                {{ browserStatus && loginStatus ? '正常' : '待初始化' }}
              </el-tag>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 最近定时任务 -->
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title"><el-icon><Calendar /></el-icon>最近定时任务</span>
        <el-button type="primary" link @click="router.push('/tasks')">
          查看全部
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </div>

      <el-empty v-if="recentTasks.length === 0" description="暂无定时任务，快去添加一个吧">
        <el-button type="primary" @click="router.push('/tasks')">添加任务</el-button>
      </el-empty>

      <el-table v-else :data="recentTasks" stripe class="task-table">
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column label="好友" min-width="140">
          <template #default="{ row }">
            <div class="friend-cell">
              <span class="friend-avatar">{{ row.name?.charAt(0) || '?' }}</span>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="120" align="center">
          <template #default="{ row }">
            <el-tag type="warning" effect="plain">{{ row.time }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="下次执行" min-width="180">
          <template #default="{ row }">
            <span class="next-run">
              <el-icon><Clock /></el-icon>
              {{ row.next_run || '未设置' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  Monitor,
  Clock,
  Key,
  User,
  Operation,
  Setting,
  InfoFilled,
  Calendar,
  ArrowRight,
  TopRight
} from '@element-plus/icons-vue'
import { initBrowser as initBrowserApi, getInitStatus, getLoginStatus, getFriendsList, getTaskList, getHome } from '../api/douyin'
import { browserStatus, loginStatus, setBrowserStatus, setLoginStatus, setFriendsList } from '../stores/browser'
import { formatFriendsList } from '../utils/format'
import { APP_VERSION, API_HOST, FRONTEND_PORT } from '../config'

const router = useRouter()

// 键盘触发可点击块的点击事件（Enter / Space）
const onActionKeydown = (e) => {
  e.currentTarget.click()
}

const friendsCount = ref(0)
const taskCount = ref(0)
const recentTasks = ref([])
const initLoading = ref(false)
const uptime = ref('--')
const refreshing = ref(false)

// noVNC 网页版地址（用当前访问的域名/IP 拼 6080 端口，便于一键打开 VNC 二次验证）
const vncUrl = `http://${window.location.hostname}:6080/`

// 数字滚动动画（好友数/任务数变化时平滑递增）
const friendsDisplay = ref(0)
const tasksDisplay = ref(0)
let countRaf = null
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)
const animateCount = (from, to, duration, setter) => {
  if (countRaf) cancelAnimationFrame(countRaf)
  if (from === to) {
    setter(to)
    return
  }
  const start = performance.now()
  const step = (now) => {
    const p = Math.min((now - start) / duration, 1)
    setter(Math.round(from + (to - from) * easeOutCubic(p)))
    if (p < 1) countRaf = requestAnimationFrame(step)
  }
  countRaf = requestAnimationFrame(step)
}

const formatUptime = (startTime) => {
  const start = new Date(startTime)
  const now = new Date()
  const diff = Math.floor((now - start) / 1000)
  if (!Number.isFinite(diff) || diff < 0) return '--'
  const days = Math.floor(diff / 86400)
  const hours = Math.floor((diff % 86400) / 3600)
  const minutes = Math.floor((diff % 3600) / 60)
  const seconds = diff % 60
  const parts = []
  if (days > 0) parts.push(`${days}天`)
  if (hours > 0 || days > 0) parts.push(`${hours}小时`)
  if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}分`)
  parts.push(`${seconds}秒`)
  return parts.join(' ')
}

const checkBrowserStatus = async () => {
  try {
    const res = await getInitStatus()
    browserStatus.value = res.data === 'Yes'
    setBrowserStatus(browserStatus.value)
  } catch (error) {
    browserStatus.value = false
    setBrowserStatus(false)
  }
}

const checkLoginStatus = async () => {
  try {
    const res = await getLoginStatus()
    loginStatus.value = res.data === 'Yes'
    setLoginStatus(loginStatus.value)
  } catch (error) {
    loginStatus.value = false
    setLoginStatus(false)
  }
}

const refreshFriends = async () => {
  try {
    const res = await getFriendsList()
    setFriendsList(formatFriendsList(res.data.list))
    friendsCount.value = res.data.count || 0
    animateCount(friendsDisplay.value, friendsCount.value, 700, v => (friendsDisplay.value = v))
    ElMessage.success('刷新成功')
  } catch (error) {
    // 错误提示已由响应拦截器统一处理
  }
}

const loadTaskList = async () => {
  try {
    const res = await getTaskList()
    taskCount.value = res.data.count || 0
    animateCount(tasksDisplay.value, taskCount.value, 700, v => (tasksDisplay.value = v))
    recentTasks.value = res.data.tasks?.slice(0, 5) || []
  } catch (error) {
    console.error('加载任务列表失败:', error)
  }
}

const initBrowser = async () => {
  initLoading.value = true
  try {
    const res = await initBrowserApi()
    if (res.code === 200) {
      browserStatus.value = true
      setBrowserStatus(true)
      ElMessage.success('浏览器初始化成功')
      await checkLoginStatus()
      if (!loginStatus.value) {
        ElMessageBox.confirm('浏览器初始化成功，但您还未登录抖音账号，是否前往登录？', '提示', {
          confirmButtonText: '前往登录',
          cancelButtonText: '稍后',
          type: 'warning'
        }).then(() => {
          router.push('/settings')
        }).catch(() => {})
      }
    }
  } catch (error) {
    // 错误提示已由响应拦截器统一处理
  } finally {
    initLoading.value = false
  }
}

// 手动刷新全部数据
const refreshAll = async () => {
  refreshing.value = true
  try {
    await checkBrowserStatus()
    await checkLoginStatus()
    if (browserStatus.value && loginStatus.value) {
      await refreshFriends()
      await loadTaskList()
    }
  } finally {
    refreshing.value = false
  }
}

let uptimeTimer = null

onMounted(async () => {
  await refreshAll()
  // 获取并缓存运行时长
  try {
    const res = await getHome()
    const timeKey = res.time
    if (timeKey) {
      uptime.value = formatUptime(timeKey)
      uptimeTimer = setInterval(() => {
        uptime.value = formatUptime(timeKey)
      }, 1000)
    }
  } catch (error) {
    uptime.value = '获取失败'
  }
})

onUnmounted(() => {
  if (uptimeTimer) {
    clearInterval(uptimeTimer)
    uptimeTimer = null
  }
  if (countRaf) {
    cancelAnimationFrame(countRaf)
    countRaf = null
  }
})
</script>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
}

/* 首屏内容级联入场 */
.page > * {
  animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.page > *:nth-child(1) {
  animation-delay: 0.02s;
}
.page > *:nth-child(2) {
  animation-delay: 0.08s;
}
.page > *:nth-child(3) {
  animation-delay: 0.14s;
}
.page > *:nth-child(4) {
  animation-delay: 0.2s;
}

/* ---------- 欢迎横幅 ---------- */
.hero {
  position: relative;
  border-radius: var(--radius-xl);
  padding: 30px 34px;
  overflow: hidden;
  background: var(--gradient);
  background-size: 200% 200%;
  animation: gradientShift 9s ease-in-out infinite;
  box-shadow: 0 14px 34px rgba(255, 90, 47, 0.28);
}

.hero::after {
  content: '';
  position: absolute;
  right: -60px;
  top: -80px;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
}

.hero-inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-title {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.01em;
}

.hero-subtitle {
  margin-top: 6px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-actions .el-button {
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(255, 255, 255, 0.9);
  color: var(--primary);
  font-weight: 600;
}

.hero-actions .el-button:hover {
  background: #fff;
  color: var(--primary-strong);
}

.hero-tag {
  border-color: rgba(255, 255, 255, 0.6);
  color: #fff;
  background: rgba(255, 255, 255, 0.18);
}

/* ---------- 状态卡片 ---------- */
.stat-row {
  row-gap: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.3s ease,
    border-color 0.3s ease;
  height: 100%;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 22px;
}

.stat-icon.browser { background: var(--primary-soft); color: var(--primary); }
.stat-icon.login { background: var(--info-bg); color: var(--info); }
.stat-icon.friends { background: var(--success-bg); color: var(--success); }
.stat-icon.tasks { background: var(--warning-bg); color: var(--warning); }

.stat-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stat-label {
  font-size: 13px;
  color: var(--text-3);
  margin-bottom: 2px;
}

.stat-value {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-1);
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}

.stat-value.number {
  font-size: 22px;
  font-weight: 700;
}

.stat-value.number em {
  font-style: normal;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-3);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot.online { background: var(--success); box-shadow: 0 0 0 3px rgba(22,163,74,.15); }
.dot.offline { background: var(--danger); box-shadow: 0 0 0 3px rgba(239,68,68,.15); }

/* ---------- 面板 ---------- */
.main-row {
  row-gap: 20px;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 22px;
  height: 100%;
  transition: transform 0.25s ease, box-shadow 0.25s ease, background-color 0.3s ease,
    border-color 0.3s ease;
}

.panel:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.panel + .panel {
  margin-top: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-title .el-icon {
  color: var(--primary);
  font-size: 18px;
}

/* ---------- 快速操作 ---------- */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 16px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-item:hover {
  border-color: var(--primary);
  background: var(--primary-soft);
  transform: translateY(-1px);
}

.action-item.loading {
  opacity: 0.65;
  pointer-events: none;
}

.action-icon {
  width: 44px;
  height: 44px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 20px;
  color: #fff;
}

.action-icon.browser { background: linear-gradient(135deg, #ff8a3d, #ff4d5e); }
.action-icon.refresh { background: linear-gradient(135deg, #3b82f6, #6366f1); }
.action-icon.tasks { background: linear-gradient(135deg, #16a34a, #22c55e); }
.action-icon.settings { background: linear-gradient(135deg, #f59e0b, #f97316); }

.action-text {
  display: flex;
  flex-direction: column;
}

.action-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.action-hint {
  font-size: 12px;
  color: var(--text-3);
}

/* ---------- 系统信息 ---------- */
.info-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  background: var(--surface-2);
  border-radius: var(--radius-md);
}

.info-label {
  font-size: 13px;
  color: var(--text-3);
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-value.uptime {
  color: var(--success);
  font-variant-numeric: tabular-nums;
}

.info-item .vnc-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--info);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.info-item .vnc-link:hover {
  text-decoration: underline;
}

/* ---------- 最近任务 ---------- */
.task-table {
  margin-top: 4px;
}

.friend-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.friend-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
}

.next-run {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-2);
  font-size: 13px;
}

.next-run .el-icon {
  color: var(--text-3);
}

/* ---------- 响应式 ---------- */
@media (max-width: 768px) {
  .hero {
    padding: 24px 22px;
  }

  .hero-title {
    font-size: 20px;
  }

  .action-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .panel {
    padding: 18px;
  }
}

@media (max-width: 480px) {
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
