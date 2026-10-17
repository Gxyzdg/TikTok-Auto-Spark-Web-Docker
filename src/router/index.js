import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

// 路由配置
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    // 首次登录（一次性随机密码）强制改密页：不套用后台布局
    path: '/setup',
    name: 'Setup',
    component: () => import('../views/Setup.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    meta: { requiresAuth: true },
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('../views/Home.vue'),
        meta: { title: '首页', icon: 'House' }
      },
      {
        path: 'friends',
        name: 'Friends',
        component: () => import('../views/Friends.vue'),
        meta: { title: '好友列表', icon: 'User' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('../views/Tasks.vue'),
        meta: { title: '定时任务', icon: 'Clock' }
      },
      {
        path: 'wizard',
        name: 'Wizard',
        component: () => import('../views/Wizard.vue'),
        meta: { title: '登录向导', icon: 'Connection' }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('../views/Settings.vue'),
        meta: { title: '设置', icon: 'Setting' }
      },
      {
        path: ':pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('../views/NotFound.vue'),
        meta: { title: '页面不存在', icon: 'QuestionFilled' }
      }
    ]
  }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from) => {
  const userStore = useUserStore()

  // 需要登录的页面
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    return '/login'
  }
  if (to.path === '/login' && userStore.isLoggedIn) {
    return userStore.userInfo.mustChangePassword ? '/setup' : '/'
  }
  // 未完成首次改密时，任何后台页面都先回强制改密页
  if (
    userStore.isLoggedIn &&
    userStore.userInfo.mustChangePassword &&
    to.path !== '/setup' &&
    to.path !== '/login'
  ) {
    return '/setup'
  }
})

export default router
