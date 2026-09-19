<template>
  <div class="layout">
    <!-- 移动端遮罩 -->
    <div
      v-if="isMobile && sidebarVisible"
      class="overlay"
      @click="closeSidebar"
    ></div>

    <!-- 侧边栏 -->
    <aside
      class="sidebar"
      :class="{
        'is-collapsed': isCollapsed && !isMobile,
        'is-mobile': isMobile,
        'is-mobile-open': sidebarVisible
      }"
    >
      <div class="logo">
        <div class="logo-mark"><FlameIcon /></div>
        <span v-if="!isCollapsed || isMobile" class="logo-text">抖音火花助手</span>
        <el-tooltip
          :content="browserStatus ? '浏览器已初始化' : '浏览器未初始化'"
          placement="right"
        >
          <span class="status-dot" :class="browserStatus ? 'online' : 'offline'"></span>
        </el-tooltip>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed && !isMobile"
        :collapse-transition="false"
        class="menu"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in menuList"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>
            <span>{{ item.title }}</span>
          </template>
        </el-menu-item>
      </el-menu>

      <div v-if="!isCollapsed || isMobile" class="sidebar-footer">
        <a class="sidebar-footer__link" :href="vncUrl" target="_blank" rel="noopener">
          <el-icon><Monitor /></el-icon>
          <span>noVNC 远程桌面</span>
        </a>
        <span class="sidebar-footer__ver mono">{{ APP_VERSION }}</span>
      </div>
    </aside>

    <!-- 主体 -->
    <div class="main">
      <header class="header">
        <div class="header-left">
          <el-icon
            class="collapse-btn"
            role="button"
            tabindex="0"
            :aria-label="isCollapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="toggleSidebar"
            @keydown.enter="toggleSidebar"
            @keydown.space.prevent="toggleSidebar"
          >
            <Fold v-if="!isCollapsed || isMobile" />
            <Expand v-else />
          </el-icon>
          <div class="header-titles">
            <h1 class="header-title">{{ currentMenuTitle }}</h1>
            <p class="header-sub">{{ currentMenuSubtitle }}</p>
          </div>
        </div>

        <div class="header-right">
          <el-tooltip :content="isDark ? '切换亮色模式' : '切换暗色模式'" placement="bottom">
            <el-icon
              class="theme-toggle"
              role="button"
              tabindex="0"
              :aria-label="isDark ? '切换亮色模式' : '切换暗色模式'"
              @click="toggleDark"
              @keydown.enter="toggleDark"
              @keydown.space.prevent="toggleDark"
            >
              <Sunny v-if="isDark" />
              <Moon v-else />
            </el-icon>
          </el-tooltip>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info" tabindex="0" aria-label="用户菜单">
              <el-avatar :size="32" :src="douyinAvatar" :icon="UserFilled" class="douyin-avatar" />
              <span class="username">{{ userStore.userInfo.username || 'Admin' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <router-view v-slot="{ Component, route }">
          <Transition name="page" mode="out-in" appear>
            <component :is="Component" :key="route.path" />
          </Transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '../stores/user'
import { logout, getInitStatus, getLoginStatus, getUserInfo } from '../api/douyin'
import { browserStatus, loginStatus, setBrowserStatus, setLoginStatus, douyinAvatar, setDouyinUser } from '../stores/browser'
import FlameIcon from '../components/FlameIcon.vue'
import { APP_VERSION } from '../config'
import {
  Fold,
  Expand,
  UserFilled,
  ArrowDown,
  SwitchButton,
  House,
  User,
  Clock,
  Setting,
  Monitor,
  Moon,
  Sunny
} from '@element-plus/icons-vue'

const vncUrl = `http://${window.location.hostname}:6080/`

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isCollapsed = ref(false)
const isMobile = ref(false)
const sidebarVisible = ref(false)
const isDark = ref(document.documentElement.classList.contains('dark'))

const toggleDark = () => {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    isCollapsed.value = true
    sidebarVisible.value = false
  } else {
    sidebarVisible.value = true
  }
}

const toggleSidebar = () => {
  if (isMobile.value) {
    sidebarVisible.value = !sidebarVisible.value
  } else {
    isCollapsed.value = !isCollapsed.value
  }
}

const closeSidebar = () => {
  if (isMobile.value) {
    sidebarVisible.value = false
  }
}

// 全局轮询浏览器/登录状态，保持侧边栏状态点实时
let statusTimer = null
const pollStatus = async () => {
  try {
    const res = await getInitStatus()
    setBrowserStatus(res.data === 'Yes')
  } catch (e) {
    setBrowserStatus(false)
  }
  try {
    const res = await getLoginStatus()
    setLoginStatus(res.data === 'Yes')
  } catch (e) {
    setLoginStatus(false)
  }
  // 已登录且尚无头像缓存时，拉取抖音账号头像
  if (loginStatus.value && !douyinAvatar.value) {
    await loadDouyinUser()
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  pollStatus()
  statusTimer = setInterval(pollStatus, 30000)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
})

const menuList = [
  { path: '/home', title: '概览', sub: '运行状态与快捷操作', icon: House },
  { path: '/friends', title: '好友列表', sub: '好友数据与火花状态', icon: User },
  { path: '/tasks', title: '定时任务', sub: '每日自动发送任务', icon: Clock },
  { path: '/settings', title: '设置', sub: '账号登录与系统配置', icon: Setting }
]

const activeMenu = computed(() => route.path)

const currentMenuTitle = computed(() => {
  const menu = menuList.find(item => item.path === activeMenu.value)
  return menu ? menu.title : '概览'
})

const currentMenuSubtitle = computed(() => {
  const menu = menuList.find(item => item.path === activeMenu.value)
  return menu ? menu.sub : ''
})

// 登录状态下拉取抖音账号头像（右上角显示真实头像）
const loadDouyinUser = async () => {
  if (!loginStatus.value) return
  try {
    const res = await getUserInfo()
    const d = res.data || {}
    setDouyinUser(d.nickname, d.avatar)
  } catch (e) {
    // 错误已由响应拦截器统一提示
  }
}

const handleMenuSelect = (path) => {
  router.push(path)
  if (isMobile.value) {
    sidebarVisible.value = false
  }
}

const handleCommand = (command) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      type: 'warning'
    }).then(async () => {
      try {
        await logout()
      } catch (e) {}
      userStore.logout()
      router.push('/login')
    }).catch(() => {})
  }
}
</script>

<style scoped>
.layout {
  width: 100%;
  height: 100vh;
  display: flex;
  overflow: hidden;
}

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 29, 51, 0.42);
  z-index: 25;
}

/* ---------- 侧边栏 ---------- */
.sidebar {
  width: 232px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.22s ease, transform 0.22s ease, background-color 0.28s ease,
    border-color 0.28s ease;
  position: relative;
  z-index: 30;
}

.sidebar.is-collapsed {
  width: 64px;
}

.sidebar.is-mobile {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 232px;
  transform: translateX(-100%);
  box-shadow: var(--shadow-lg);
}

.sidebar.is-mobile-open {
  transform: translateX(0);
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  position: relative;
  flex-shrink: 0;
}

.logo-mark {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  color: #fff;
  background: var(--gradient);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 30%, transparent);
  flex-shrink: 0;
}

.logo-text {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  letter-spacing: -0.005em;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: auto;
  flex-shrink: 0;
}

.status-dot.online {
  background: var(--success);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 16%, transparent);
}

.status-dot.offline {
  background: var(--danger);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 16%, transparent);
  animation: softPulse 2s infinite;
}

@keyframes softPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.sidebar.is-collapsed .logo {
  justify-content: center;
  padding: 0;
}

.sidebar.is-collapsed .logo-text {
  display: none;
}

.sidebar.is-collapsed .status-dot {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 7px;
  height: 7px;
  margin: 0;
}

.menu {
  border-right: none;
  flex: 1;
  padding: 10px 10px;
  background: transparent;
  overflow-y: auto;
}

.sidebar.is-collapsed .menu {
  padding: 10px 6px;
}

.menu:not(.el-menu--collapse) {
  width: 100%;
}

.menu :deep(.el-menu-item) {
  height: 40px;
  line-height: 40px;
  margin-bottom: 2px;
  border-radius: var(--radius-md);
  color: var(--text-2);
  font-size: 13.5px;
  font-weight: 500;
  transition: background-color var(--dur) ease, color var(--dur) ease;
}

.menu :deep(.el-menu-item:hover) {
  background: var(--surface-muted);
  color: var(--text-1);
}

.menu :deep(.el-menu-item.is-active) {
  background: color-mix(in srgb, var(--primary) 10%, var(--surface));
  color: var(--primary);
  font-weight: 600;
}

.menu :deep(.el-menu-item .el-icon) {
  font-size: 17px;
  transition: color var(--dur) ease;
}

/* 侧栏底部信息区 */
.sidebar-footer {
  margin-top: auto;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sidebar-footer__link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-2);
  transition: color var(--dur) ease;
}

.sidebar-footer__link:hover {
  color: var(--primary);
}

.sidebar-footer__ver {
  font-size: 11.5px;
  color: var(--text-faint);
  white-space: nowrap;
}

/* ---------- 主体 ---------- */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header {
  min-height: 60px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 20px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 20;
  transition: background-color 0.28s ease, border-color 0.28s ease;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.header-titles {
  min-width: 0;
}

.header-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text-1);
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-sub {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.4;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.collapse-btn {
  font-size: 18px;
  cursor: pointer;
  color: var(--text-2);
  padding: 4px;
  border-radius: var(--radius-sm);
  transition: color var(--dur) ease, background-color var(--dur) ease;
}

.collapse-btn:hover {
  color: var(--primary);
  background: var(--surface-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.theme-toggle {
  font-size: 17px;
  color: var(--text-2);
  cursor: pointer;
  padding: 6px;
  border-radius: var(--radius-sm);
  transition: color var(--dur) ease, background-color var(--dur) ease;
}

.theme-toggle:hover {
  color: var(--primary);
  background: var(--surface-muted);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 5px 8px 5px 6px;
  border-radius: var(--radius-md);
  transition: background-color var(--dur) ease;
}

.user-info:hover {
  background: var(--surface-muted);
}

.username {
  font-size: 13px;
  color: var(--text-1);
  font-weight: 500;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px 24px;
}

@media (max-width: 768px) {
  .username {
    display: none;
  }

  .header {
    padding: 8px 12px;
  }

  .header-title {
    font-size: 16px;
  }

  .content {
    padding: 14px;
  }
}
</style>
