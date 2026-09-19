import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api',  // 通过 vite 代理到后端
  timeout: 30000
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token') || localStorage.getItem('douyin_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    const contentType = response.headers['content-type']
    if (contentType && contentType.includes('application/json')) {
      const res = response.data
      if (res && res.code !== undefined && res.code == 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        localStorage.removeItem('douyin_token')
        setTimeout(() => {
          window.location.replace('/login')
        }, 1500)
        return Promise.reject(new Error(res.data || '未授权'))
      }
      if (res && res.code !== undefined && res.code != 200 && res.code != '200') {
        ElMessage.error(res.data || res.msg || res.message || '请求失败')
        return Promise.reject(new Error(res.data || '请求失败'))
      }
      return res
    }
    return response
  },
  error => {
    // 处理网络错误或服务器错误
    if (error.response) {
      // 服务器返回了错误状态码
      const status = error.response.status
      const data = error.response.data

      if (status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        localStorage.removeItem('douyin_token')
        setTimeout(() => {
          window.location.replace('/login')
        }, 1500)
        return Promise.reject(error)
      } else if (status === 500) {
        ElMessage.error('服务器内部错误')
      } else if (status === 404) {
        ElMessage.error('请求的资源不存在')
      } else {
        // 尝试从响应中提取错误信息
        const msg = data?.data || data?.msg || data?.message || error.message || `请求失败 (${status})`
        ElMessage.error(msg)
      }
    } else if (error.request) {
      // 请求已发送但没有收到响应
      ElMessage.error('无法连接到服务器，请检查后端服务是否启动')
    } else {
      ElMessage.error(error.message || '网络错误')
    }
    return Promise.reject(error)
  }
)

// 初始化浏览器（首次可能联网下载 chromedriver + 冷启动 Chrome，超时放宽到 120s，与反代超时对齐）
export const initBrowser = () => api.get('/Api/Init', { timeout: 120000 })

// 重新初始化浏览器（强制关闭现有会话并重建，冷启动超时同 Init）
export const reInitBrowser = () => api.get('/Api/ReInit', { timeout: 120000 })

// 获取初始化状态
export const getInitStatus = () => api.get('/Api/GetInit')

// 获取登录状态
export const getLoginStatus = () => api.get('/Api/GetLogin')

// 扫码登录确认
export const pnglogin = () => api.get('/Api/Pnglogin')

// 获取浏览器页面截图
export const getScrlk = () => api.get('/Api/GetScrlk')

// 登录（cookie 即用户粘贴的 Base64Cookie，后端 base64 解码一次即可）
export const login = async (cookie) => {
  return api.post('/Api/login', { cooke: cookie })
}

// 获取二维码
export const getLoginPng = () => api.get('/Api/login/Init/GetLoginPng')

// 强制退出登录
export const dieLogin = () => api.get('/Api/DieLogin')

// 获取Cookie
export const getCooker = (password) => api.post('/Api/login/Init/GetCooker', { password })

// 发送验证码
export const sendVerifyCode = (areacode, phone) => api.get('/Api/LoginPhone', { params: { areacode, phone } })

// 提交验证码
export const submitVerifyCode = (code) => api.get('/Api/LoginPhoneInput', { params: { code } })

// 退出登录
export const logout = () => api.get('/Api/logout')

// 获取好友列表
export const getFriendsList = () => api.get('/Api/GetFriendsList')

// 发送消息
export const sendMessage = (name, text) => api.post('/Api/Send', { name, text })

// 添加定时任务
export const addTask = (time, name, text) => api.post('/Time/add', { time, name, text })

// 删除定时任务
export const delTask = (task_id) => api.get('/Time/del', { params: { task_id } })

// 修改定时任务
export const editTask = (name, new_time) => api.get('/Time/edit', { params: { name, new_time } })

// 停用定时任务
export const pauseTask = (task_id) => api.get('/Time/pause', { params: { task_id } })

// 启用定时任务
export const enableTask = (task_id) => api.get('/Time/enable', { params: { task_id } })

// 获取任务列表
export const getTaskList = () => api.get('/Time/getlist')

// 当前登录抖音账号信息（昵称 + 头像）
export const getUserInfo = () => api.get('/Api/GetUserInfo')

// 是否保存抖音登录数据（Cookie）
export const getSaveSession = () => api.get('/Api/GetSaveSession')

// 设置是否保存抖音登录数据（Cookie）
export const setSaveSession = (enabled) => api.post('/Api/SetSaveSession', { enabled })

// 综合运行状态（浏览器/登录/调度器/任务数）
export const getStatus = () => api.get('/Api/GetStatus')

// 远程画面：可用性与视口信息（登录向导用）
export const getScreenInfo = () => api.get('/Api/Screen/Info')

// 远程画面：签发一次性 WebSocket 连接票据
export const getScreenTicket = () => api.get('/Api/Screen/Ticket')

// 获取用户名
export const getUsername = () => api.get('/Api/GetUsername')

// 修改密码
export const changePassword = (old_password, new_password) => api.post('/Api/ChangePassword', { old_password, new_password })

// 获取上次登录IP
export const getLastLoginIP = () => api.get('/Api/GetLastLoginIP')

// 强制登录状态
export const forceLogin = () => api.get('/Api/LoginDebug')

// 获取项目启动时间
export const getHome = () => api.get('/Home')

export default api
