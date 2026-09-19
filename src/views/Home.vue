<template>
  <div class="page">
    <!-- 账号状态条 -->
    <section class="status-strip">
      <div class="status-strip__main">
        <div class="brand-mark"><FlameIcon /></div>
        <div class="status-strip__text">
          <div class="status-strip__title">
            {{ loginStatus && douyinNickname ? douyinNickname : '抖音账号未登录' }}
          </div>
          <div class="status-strip__sub">
            好友 <b>{{ friendsCount }}</b> 位 · 定时任务 <b>{{ taskCount }}</b> 个 · 调度器
            {{ schedulerStatus ? '运行中' : '未运行' }}
          </div>
        </div>
      </div>
      <div class="status-strip__actions">
        <el-tag :type="runState.type" effect="light" round class="status-tag">
          <i class="dot" :class="runState.dot"></i>
          {{ runState.text }}
        </el-tag>
        <el-button :icon="Refresh" @click="refreshAll" :loading="refreshing">刷新</el-button>
      </div>
    </section>

    <!-- 状态卡片 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :xs="12" :sm="12" :md="12" :lg="6">
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

      <el-col :xs="12" :sm="12" :md="12" :lg="6">
        <div class="stat-card">
          <div class="stat-icon login"><el-icon><Key /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">登录状态</span>
            <span class="stat-value">
              <i class="dot" :class="loginStatus ? 'online' : 'offline'"></i>
              {{ loginStatus ? (douyinNickname ? '已登录 · ' + douyinNickname : '已登录') : '未登录' }}
            </span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="12" :lg="6">
        <div class="stat-card">
          <div class="stat-icon friends"><el-icon><User /></el-icon></div>
          <div class="stat-body">
            <span class="stat-label">好友数量</span>
            <span class="stat-value number">{{ friendsDisplay }} <em>人</em></span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="12" :lg="6">
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
      <el-col :xs="24" :lg="13">
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
              :class="{ loading: reinitLoading }"
              tabindex="0"
              role="button"
              @click="reInitBrowser"
              @keydown.enter="onActionKeydown"
              @keydown.space.prevent="onActionKeydown"
            >
              <div class="action-icon reinit"><el-icon><RefreshRight /></el-icon></div>
              <div class="action-text">
                <span class="action-name">重新初始化浏览器</span>
                <span class="action-hint">卡死/异常时重建</span>
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
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :lg="11">
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
            <div v-if="API_HOST" class="info-item">
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
                  进入 noVNC ({{ NOVNC_PORT }}) <el-icon><TopRight /></el-icon>
                </a>
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">调度器</span>
              <span class="info-value">
                <i class="dot" :class="schedulerStatus ? 'online' : 'offline'"></i>
                {{ schedulerStatus ? '运行中' : '未运行' }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">运行状态</span>
              <el-tag :type="runState.type" size="small" effect="light">
                {{ runState.text }}
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
              <el-avatar :size="32" :src="avatarOf(row.name)" class="friend-avatar-img">
                {{ row.name?.charAt(0) || '?' }}
              </el-avatar>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  RefreshRight,
  Monitor,
  Clock,
  Key,
  User,
  Operation,
  InfoFilled,
  Calendar,
  ArrowRight,
  TopRight
} from '@element-plus/icons-vue'
import { initBrowser as initBrowserApi, reInitBrowser as reInitBrowserApi, getFriendsList, getTaskList, getHome, getStatus, getUserInfo } from '../api/douyin'
import { browserStatus, loginStatus, friendsList, douyinNickname, setBrowserStatus, setLoginStatus, setFriendsList, setDouyinUser } from '../stores/browser'
import FlameIcon from '../components/FlameIcon.vue'
import { formatFriendsList } from '../utils/format'
import { APP_VERSION, API_HOST, FRONTEND_PORT, NOVNC_PORT, NOVNC_URL } from '../config'

const router = useRouter()

// 键盘触发可点击块的点击事件（Enter / Space）
const onActionKeydown = (e) => {
  e.currentTarget.click()
}

const friendsCount = ref(0)
const taskCount = ref(0)
const recentTasks = ref([])
const initLoading = ref(false)
const reinitLoading = ref(false)
const uptime = ref('--')
const refreshing = ref(false)

// 运行状态三态：未初始化 / 已初始化但未登录 / 运行正常
// 避免"浏览器已初始化但没登录"被横幅和系统信息笼统显示成"待初始化"（与状态卡片不一致）
const runState = computed(() => {
  if (browserStatus.value && loginStatus.value) {
    return { text: '系统运行正常', type: 'success', dot: 'online' }
  }
  if (browserStatus.value) {
    return { text: '待登录抖音', type: 'warning', dot: 'pending' }
  }
  return { text: '待初始化', type: 'info', dot: 'offline' }
})

// 好友名 → 抖音头像 映射：首页定时任务栏据此显示真实头像（取不到时回退首字头像）
const schedulerStatus = ref(false)

const avatarMap = computed(() => {
  const m = {}
  for (const f of friendsList.value) {
    if (f && f.name) m[f.name] = f.avatar || ''
  }
  return m
})
const avatarOf = (name) => avatarMap.value[name] || ''

// noVNC 网页版地址（端口跟随容器 NOVNC_PORT 环境变量，不再写死）
const vncUrl = NOVNC_URL

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

// 综合状态检测：浏览器是否可用、抖音是否已登录、调度器是否运行（后端实际校验）
const checkStatus = async () => {
  try {
    const res = await getStatus()
    const d = res.data || {}
    browserStatus.value = d.browser === 'Yes'
    setBrowserStatus(browserStatus.value)
    loginStatus.value = d.login === 'Yes'
    setLoginStatus(loginStatus.value)
    schedulerStatus.value = d.scheduler === 'Yes'
    taskCount.value = d.task_count ?? taskCount.value
    if (loginStatus.value && !douyinNickname.value) {
      loadDouyinUser()
    }
  } catch (error) {
    browserStatus.value = false
    loginStatus.value = false
    schedulerStatus.value = false
    setBrowserStatus(false)
    setLoginStatus(false)
  }
}

const loadDouyinUser = async () => {
  try {
    const res = await getUserInfo()
    const d = res.data || {}
    setDouyinUser(d.nickname, d.avatar)
  } catch (e) {
    // 错误已由响应拦截器统一提示
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
      if (res.data === 'init Repeated!') {
        ElMessage.info('浏览器已在运行中，无需重复初始化')
      } else {
        ElMessage.success('浏览器初始化成功')
      }
      await checkStatus()
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

// 重新初始化浏览器：关闭当前会话并重建（登录状态可能失效，先确认）
const reInitBrowser = async () => {
  try {
    await ElMessageBox.confirm(
      '将关闭当前浏览器会话并重新启动（约需 10~30 秒）。未开启「保存登录数据」时抖音登录状态会失效，需要重新登录，是否继续？',
      '重新初始化浏览器',
      {
        confirmButtonText: '确定重新初始化',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch (e) {
    return
  }

  reinitLoading.value = true
  try {
    const res = await reInitBrowserApi()
    if (res.code === 200) {
      ElMessage.success('浏览器已重新初始化')
      await checkStatus()
      if (!loginStatus.value) {
        ElMessageBox.confirm('浏览器已重启，请重新登录抖音账号，是否现在前往登录？', '提示', {
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
    reinitLoading.value = false
  }
}

// 手动刷新全部数据
const refreshAll = async () => {
  refreshing.value = true
  try {
    await checkStatus()
    // 定时任务是本地持久化数据，未登录/未初始化时也要展示，否则卡片会一直是 0
    await loadTaskList()
    if (browserStatus.value && loginStatus.value) {
      await refreshFriends()
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
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

/* ---------- 账号状态条 ---------- */
.status-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 18px;
  background: var(--surface);
  background-image: var(--bg-accent);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.status-strip__main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-mark {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: var(--radius-md);
  display: grid;
  place-items: center;
  font-size: 19px;
  color: #fff;
  background: var(--gradient);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 28%, transparent);
}

.status-strip__text {
  min-width: 0;
}

.status-strip__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-strip__sub {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-strip__sub b {
  color: var(--text-2);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.status-strip__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  border-color: transparent;
  font-weight: 500;
}

.status-tag .dot {
  margin-right: 6px;
}

/* ---------- 指标卡片 ---------- */
.stat-row {
  row-gap: 14px;
}

.stat-card {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
  transition: transform var(--dur) ease, box-shadow var(--dur) ease,
    border-color var(--dur) ease, background-color 0.28s ease;
}

.stat-card::after {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 2px;
  background: linear-gradient(90deg, var(--primary), transparent);
  opacity: 0.75;
}

.stat-card:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
  box-shadow: var(--shadow-md);
}

.stat-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 17px;
}

.stat-icon.browser { color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, transparent); }
.stat-icon.login { color: var(--info); background: color-mix(in srgb, var(--info) 12%, transparent); }
.stat-icon.friends { color: var(--success); background: color-mix(in srgb, var(--success) 12%, transparent); }
.stat-icon.tasks { color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, transparent); }

.stat-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stat-label {
  font-size: 12px;
  color: var(--text-3);
  margin-bottom: 1px;
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.stat-value.number {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.stat-value.number em {
  font-style: normal;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-3);
}

/* ---------- 面板 ---------- */
.main-row {
  row-gap: 14px;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 18px;
  height: 100%;
  transition: box-shadow var(--dur) ease, background-color 0.28s ease,
    border-color 0.28s ease;
}

.panel + .panel {
  margin-top: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
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

/* ---------- 快速操作 ---------- */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: border-color var(--dur) ease, background var(--dur) ease,
    transform var(--dur) ease;
}

.action-item:hover {
  border-color: color-mix(in srgb, var(--primary) 45%, var(--border));
  background: color-mix(in srgb, var(--primary) 4%, var(--surface));
  transform: translateY(-1px);
}

.action-item.loading {
  opacity: 0.6;
  pointer-events: none;
}

.action-icon {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
}

.action-icon.browser { color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, transparent); }
.action-icon.refresh { color: var(--info); background: color-mix(in srgb, var(--info) 12%, transparent); }
.action-icon.reinit { color: var(--slate); background: color-mix(in srgb, var(--slate) 14%, transparent); }
.action-icon.tasks { color: var(--success); background: color-mix(in srgb, var(--success) 12%, transparent); }

.action-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.action-name {
  font-size: 13.5px;
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
  gap: 6px;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: var(--surface-muted);
  border-radius: var(--radius-md);
}

.info-label {
  font-size: 12.5px;
  color: var(--text-3);
  white-space: nowrap;
}

.info-value {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-1);
  max-width: 62%;
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
  font-size: 12.5px;
  font-weight: 500;
  white-space: nowrap;
}

.info-item .vnc-link:hover {
  text-decoration: underline;
}

/* ---------- 最近任务 ---------- */
.task-table {
  margin-top: 2px;
}

.friend-cell {
  display: flex;
  align-items: center;
  gap: 9px;
}

.friend-avatar-img {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  background: var(--gradient);
  color: #fff;
  font-weight: 600;
  font-size: 12px;
}

.next-run {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-2);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
}

.next-run .el-icon {
  color: var(--text-3);
}

/* ---------- 响应式 ---------- */
@media (max-width: 768px) {
  .status-strip {
    padding: 12px 14px;
  }

  .action-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .panel {
    padding: 15px;
  }
}

@media (max-width: 480px) {
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
