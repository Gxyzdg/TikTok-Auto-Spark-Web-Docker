import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import router from './router'
import App from './App.vue'
import './style.css'

// 初始化主题（暗色/亮色），避免闪烁
const savedTheme = localStorage.getItem('theme')
if (savedTheme === 'dark') {
  document.documentElement.classList.add('dark')
}

const app = createApp(App)

// Pinia
app.use(createPinia())

// 路由
app.use(router)

// Element Plus
app.use(ElementPlus, { locale: zhCn })

// 图标均为各页面按需 import，不在此全局注册（避免强制打包全部几百个图标）

app.mount('#app')