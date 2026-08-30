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
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/home' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="activeMenu !== '/home'">
              {{ currentMenuTitle }}
            </el-breadcrumb-item>
          </el-breadcrumb>
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
              <el-avatar :size="32" :icon="UserFilled" />
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
import { logout, getInitStatus, getLoginStatus } from '../api/douyin'
import { browserStatus, setBrowserStatus, setLoginStatus } from '../stores/browser'
import FlameIcon from '../components/FlameIcon.vue'
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
  Moon,
  Sunny
} from '@element-plus/icons-vue'

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
  { path: '/home', title: '首页', icon: House },
  { path: '/friends', title: '好友列表', icon: User },
  { path: '/tasks', title: '定时任务', icon: Clock },
  { path: '/settings', title: '设置', icon: Setting }
]

const activeMenu = computed(() => route.path)

const currentMenuTitle = computed(() => {
  const menu = menuList.find(item => item.path === activeMenu.value)
  return menu ? menu.title : ''
})

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
  background: rgba(17, 24, 39, 0.45);
  z-index: 25;
}

/* ---------- 侧边栏 ---------- */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease, transform 0.25s ease, background-color 0.3s ease,
    border-color 0.3s ease;
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
  width: 240px;
  transform: translateX(-100%);
  box-shadow: var(--shadow-lg);
}

.sidebar.is-mobile-open {
  transform: translateX(0);
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  position: relative;
}

.logo-mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: #fff;
  background: var(--gradient);
  box-shadow: 0 6px 14px rgba(255, 90, 47, 0.3);
  flex-shrink: 0;
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-left: auto;
  flex-shrink: 0;
}

.status-dot.online {
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.15);
}

.status-dot.offline {
  background: var(--danger);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
  animation: pulse 2s infinite;
}

@keyframes pulse {
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
  top: 15px;
  right: 15px;
  width: 8px;
  height: 8px;
  margin: 0;
}

.menu {
  border-right: none;
  flex: 1;
  padding: 14px 12px;
  background: transparent;
  overflow-y: auto;
}

.sidebar.is-collapsed .menu {
  padding: 14px 0;
}

.menu:not(.el-menu--collapse) {
  width: 100%;
}

.menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin-bottom: 4px;
  border-radius: 10px;
  color: var(--text-2);
  font-weight: 500;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.menu :deep(.el-menu-item:hover) {
  background: var(--surface-2);
  color: var(--text-1);
}

.menu :deep(.el-menu-item.is-active) {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}

/* 菜单图标微动效：hover 轻微放大，提升操作流畅感 */
.menu :deep(.el-menu-item .el-icon) {
  transition: transform 0.2s ease;
}
.menu :deep(.el-menu-item:hover .el-icon) {
  transform: scale(1.12);
}
.menu :deep(.el-menu-item.is-active .el-icon) {
  transform: scale(1.08);
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
  height: 60px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  flex-shrink: 0;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: var(--text-2);
  transition: color 0.2s ease;
}

.collapse-btn:hover {
  color: var(--primary);
}

.header-right {
  display: flex;
  align-items: center;
}

.theme-toggle {
  font-size: 18px;
  color: var(--text-2);
  cursor: pointer;
  margin-right: 14px;
  transition: color 0.2s ease;
}

.theme-toggle:hover {
  color: var(--primary);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 8px;
  transition: background-color 0.2s ease;
}

.user-info:hover {
  background: var(--surface-2);
}

.username {
  font-size: 14px;
  color: var(--text-1);
  font-weight: 500;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
}

@media (max-width: 768px) {
  .username {
    display: none;
  }

  .content {
    padding: 14px;
  }
}
</style>
