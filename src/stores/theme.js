import { ref } from 'vue'

// 主题（暗色 / 亮色）：全应用共享 + 持久化到 localStorage
// 除本模块外不要直接改 document.documentElement.classList，避免状态不同步。
const STORAGE_KEY = 'theme'

const readSaved = () => {
  try {
    return localStorage.getItem(STORAGE_KEY) || ''
  } catch (e) {
    return ''
  }
}

/** 当前是否为暗色模式（默认亮色，用户选择后持久化） */
export const isDark = ref(readSaved() === 'dark')

/** 把主题应用到根元素（供首屏 / 切换时调用） */
export const applyTheme = (dark) => {
  const root = document.documentElement
  root.classList.toggle('dark', !!dark)
  root.style.colorScheme = dark ? 'dark' : 'light'
}

/** 设置主题并持久化 */
export const setTheme = (dark) => {
  isDark.value = !!dark
  applyTheme(isDark.value)
  try {
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
  } catch (e) {}
}

/** 在暗色 / 亮色之间切换 */
export const toggleTheme = () => setTheme(!isDark.value)

// 模块加载即应用一次（首屏由 index.html 内联脚本提前设置，这里保证状态一致）
applyTheme(isDark.value)
