<template>
  <div class="page">
    <div class="page-header animate-fade-in-up">
      <div>
        <div class="page-header__title">设置</div>
        <div class="page-header__subtitle">账户登录、密码与系统配置</div>
      </div>
    </div>

    <!-- 账户配置 -->
    <el-card shadow="never">
      <template #header>
        <span class="card-title">账户配置</span>
      </template>

      <div class="account-status">
        <span class="status-label">登录状态</span>
        <el-tag :type="loginStatus ? 'success' : 'danger'" effect="light" round>
          {{ loginStatus ? (username ? '已登录: ' + username : '已登录') : '未登录' }}
        </el-tag>
      </div>

      <div class="section-divider"></div>

      <div class="login-actions">
        <el-button type="primary" :icon="Key" @click="handleLogin" :loading="loginLoading" :disabled="loginStatus">
          扫码登录
        </el-button>
        <el-button :icon="Message" @click="phoneDialogVisible = true" :disabled="loginStatus">
          验证码登录
        </el-button>
        <el-button :icon="Edit" @click="manualDialogVisible = true" :disabled="loginStatus">
          手动登录
        </el-button>
        <el-button :icon="Document" @click="cookieDialogVisible = true">
          获取Base64Cookie
        </el-button>
        <el-button :icon="Refresh" @click="handleRefreshStatus" :loading="refreshStatusLoading">
          刷新状态
        </el-button>
        <el-button type="danger" plain :icon="SwitchButton" @click="handleDieLogin">
          强制退出登录
        </el-button>
      </div>
    </el-card>

    <!-- 后台配置 -->
    <el-card shadow="never" class="stack-card">
      <template #header>
        <span class="card-title">后台配置</span>
      </template>
      <div class="config-row">
        <div class="config-item">
          <span class="config-label">上次登录 IP</span>
          <span class="config-value">{{ lastLoginIP }}</span>
        </div>
        <el-button type="primary" :icon="Lock" @click="passwordDialogVisible = true">
          修改密码
        </el-button>
      </div>
    </el-card>

    <!-- 调试功能 -->
    <el-card shadow="never" class="stack-card">
      <template #header>
        <span class="card-title">调试功能</span>
      </template>
      <div class="config-row">
        <el-button :icon="Picture" @click="handleGetScreenshot" :loading="screenshotLoading">
          获取浏览器页面截图
        </el-button>
        <el-button type="warning" plain :icon="WarnTriangleFilled" @click="handleForceLogin">
          强制登录状态
        </el-button>
        <a href="https://github.com/Gxyzdg/TikTok-Auto-Spark-Web-Docker" target="_blank" rel="noopener" class="gh-link">
          <el-button type="success" plain :icon="Star">GitHub</el-button>
        </a>
        <span class="star-hint">求个 Star ⭐</span>
      </div>
    </el-card>

    <!-- 手动登录弹窗 -->
    <el-dialog v-model="manualDialogVisible" title="手动登录" width="500px" destroy-on-close>
      <el-form :model="manualForm" label-width="110px">
        <el-form-item label="Base64Cookie">
          <el-input v-model="manualForm.cookie" type="textarea" :rows="6" placeholder="请输入登录Base64Cookie" @keyup.enter="handleManualLogin" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="manualDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleManualLogin" :loading="manualLoading">验证登录</el-button>
      </template>
    </el-dialog>

    <!-- 获取Cookie弹窗 -->
    <el-dialog v-model="cookieDialogVisible" title="获取Base64Cookie" width="400px" destroy-on-close>
      <el-form :model="cookieForm" label-width="90px">
        <el-form-item label="确认密码">
          <el-input v-model="cookieForm.password" type="password" placeholder="请输入密码确认" @keyup.enter="handleGetCookie" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cookieDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleGetCookie" :loading="cookieLoading">获取Cookie</el-button>
      </template>
    </el-dialog>

    <!-- 验证码登录弹窗 -->
    <el-dialog v-model="phoneDialogVisible" title="验证码登录" width="420px" destroy-on-close>
      <el-form :model="phoneForm" label-width="70px">
        <el-form-item label="手机号">
          <div class="phone-row">
            <el-input v-model="phoneForm.areacode" placeholder="+86" style="width: 76px; flex-shrink: 0" @keyup.enter="handleSendCode" />
            <el-input v-model="phoneForm.phone" placeholder="请输入手机号" style="flex: 1" @keyup.enter="handleSendCode" />
          </div>
        </el-form-item>
        <el-form-item label="验证码">
          <div class="phone-row">
            <el-input v-model="phoneForm.code" placeholder="请输入验证码" style="flex: 1" @keyup.enter="handlePhoneLogin" />
            <el-button @click="handleSendCode" :disabled="codeCountdown > 0" :loading="codeLoading">
              {{ codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码' }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="phoneDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handlePhoneLogin" :loading="phoneLoading">登录</el-button>
      </template>
    </el-dialog>

    <!-- 二维码弹窗 -->
    <el-dialog v-model="qrDialogVisible" title="抖音扫码登录" width="360px" destroy-on-close>
      <div class="qrcode-container">
        <div v-if="qrcodeUrl" class="qrcode-wrapper">
          <img :src="qrcodeUrl" alt="登录二维码" class="qrcode-img" />
          <p class="qrcode-hint">请使用抖音App扫码登录</p>
        </div>
        <div v-else-if="loading" class="state-wrapper">
          <el-icon class="is-loading"><Loading /></el-icon>
          <p>正在加载二维码…</p>
        </div>
        <div v-else class="state-wrapper">
          <p>获取二维码失败，请重试</p>
        </div>
      </div>
      <div class="qrcode-actions">
        <el-button :icon="Refresh" @click="handleRefreshCode" :loading="refreshLoading" size="small">刷新验证码</el-button>
        <el-button :icon="View" @click="handleCheckLogin" :loading="checkLoading" size="small">获取登录状态</el-button>
      </div>
    </el-dialog>

    <!-- 检测登录状态 · 二次确认弹窗（提示先完成 VNC 二次验证） -->
    <el-dialog v-model="checkConfirmVisible" title="检测登录状态" width="420px" destroy-on-close>
      <div class="check-tip">
        <p>请先在 <b>VNC（noVNC）</b> 里完成抖音二次验证（如滑块、确认登录），再点击下方「确认检测」获取登录状态。</p>
        <p class="check-tip-sub">
          VNC 地址：
          <a :href="vncUrl" target="_blank" rel="noopener" class="vnc-dialog-link">{{ vncUrl }}</a>
        </p>
      </div>
      <template #footer>
        <el-button :icon="TopRight" @click="openVnc">前往 VNC</el-button>
        <el-button @click="checkConfirmVisible = false">取消</el-button>
        <el-button type="success" :loading="checkLoading" @click="handleConfirmCheck">确认检测</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="400px" destroy-on-close>
      <el-form :model="passwordForm" label-width="80px">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.old_password" type="password" placeholder="请输入原密码" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new_password" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="passwordForm.confirm_password" type="password" placeholder="请再次输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword" :loading="passwordLoading">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 截图预览弹窗 -->
    <el-dialog v-model="screenshotPreviewVisible" title="浏览器截图" width="640px" destroy-on-close>
      <img :src="screenshotUrl" alt="浏览器截图" class="screenshot-img" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Key, Refresh, View, Loading, Edit, Lock, Document, SwitchButton, Picture, Message, WarnTriangleFilled, Star, TopRight } from '@element-plus/icons-vue'
import { getLoginStatus, initBrowser, getLoginPng, login, getUsername, changePassword, getLastLoginIP, getFriendsList, getCooker, pnglogin, getScrlk, dieLogin, sendVerifyCode, submitVerifyCode, forceLogin } from '../api/douyin'
import { loginStatus, setLoginStatus, setFriendsList } from '../stores/browser'
import { formatFriendsList } from '../utils/format'

const loginLoading = ref(false)
const refreshLoading = ref(false)
const checkLoading = ref(false)
const refreshStatusLoading = ref(false)
const qrDialogVisible = ref(false)
const qrcodeUrl = ref('')
const loading = ref(false)
// 检测登录状态前的二次确认弹窗
const checkConfirmVisible = ref(false)
const vncUrl = `http://${window.location.hostname}:6080/`
const manualDialogVisible = ref(false)
const manualLoading = ref(false)
const manualForm = ref({
  cookie: ''
})
const username = ref('')  // 账号信息不持久化，每次进入实时获取
const passwordDialogVisible = ref(false)
const passwordLoading = ref(false)
const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
const lastLoginIP = ref(localStorage.getItem('douyin_last_login_ip') || '加载中...')
const settingsLoaded = ref(localStorage.getItem('douyin_settings_loaded') === '1')
const cookieDialogVisible = ref(false)
const cookieLoading = ref(false)
const cookieForm = ref({
  password: ''
})
const screenshotLoading = ref(false)
const screenshotUrl = ref('')
const screenshotPreviewVisible = ref(false)
const phoneDialogVisible = ref(false)
const phoneLoading = ref(false)
const codeLoading = ref(false)
const codeCountdown = ref(0)
let codeTimer = null
const phoneForm = ref({
  areacode: '+86',
  phone: '',
  code: ''
})

const fetchLastLoginIP = async () => {
  try {
    const res = await getLastLoginIP()
    if (res.code === 200) {
      lastLoginIP.value = res.data || '无'
      localStorage.setItem('douyin_last_login_ip', lastLoginIP.value)
    }
  } catch (error) {
    lastLoginIP.value = '获取失败'
  }
}

const fetchUsername = async () => {
  try {
    const res = await getUsername()
    if (res.code === 200) {
      username.value = res.data
    }
  } catch (error) {
    // 获取失败不提示，静默处理
  }
}

const checkLoginStatus = async () => {
  try {
    const res = await getLoginStatus()
    loginStatus.value = res.data === 'Yes'
    setLoginStatus(loginStatus.value)
    if (loginStatus.value && !username.value) {
      await fetchUsername()
    }
  } catch (error) {
    loginStatus.value = false
    setLoginStatus(false)
  }
}

const handleRefreshStatus = async () => {
  refreshStatusLoading.value = true
  try {
    username.value = ''
    await checkLoginStatus()
    await fetchLastLoginIP()
    ElMessage.success(loginStatus.value ? '已登录' : '未登录')
  } finally {
    refreshStatusLoading.value = false
  }
}

const handleCheckLogin = () => {
  // 先弹出二次确认：提示前往 VNC 完成二次验证后再检测
  checkConfirmVisible.value = true
}

const openVnc = () => {
  window.open(vncUrl, '_blank')
}

const handleConfirmCheck = () => {
  checkConfirmVisible.value = false
  doCheckLogin()
}

const doCheckLogin = async () => {
  checkLoading.value = true
  try {
    const res = await pnglogin()
    if (res.data === 'ok') {
      loginStatus.value = true
      setLoginStatus(true)
      ElMessage.success('登录成功，扫码登录窗口将关闭')
      qrDialogVisible.value = false
      checkConfirmVisible.value = false
      username.value = ''
      await fetchUsername()
      // 登录成功后请求好友列表
      await fetchFriendsList()
    } else {
      loginStatus.value = false
      setLoginStatus(false)
      ElMessage.warning('未登录，请继续扫码')
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    checkLoading.value = false
  }
}

const fetchFriendsList = async () => {
  try {
    const res = await getFriendsList()
    if (res.code === 200) {
      setFriendsList(formatFriendsList(res.data.list))
    }
  } catch (error) {
    // 获取失败静默处理
  }
}

const handleRefreshCode = async () => {
  refreshLoading.value = true
  try {
    // 先初始化浏览器
    await initBrowser()
    // 获取新二维码
    const res = await getLoginPng()
    if (res.data) {
      qrcodeUrl.value = res.data
      qrDialogVisible.value = true
      ElMessage.success('刷新成功')
    } else {
      ElMessage.error('获取二维码失败')
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    refreshLoading.value = false
  }
}

const handleManualLogin = async () => {
  if (manualLoading.value) return
  if (!manualForm.value.cookie.trim()) {
    ElMessage.warning('请输入Base64Cookie')
    return
  }
  manualLoading.value = true
  try {
    const res = await login(manualForm.value.cookie)
    if (res.data === 'ok') {
      ElMessage.success('登录成功')
      loginStatus.value = true
      setLoginStatus(true)
      manualDialogVisible.value = false
      username.value = ''
      await fetchUsername()
      await fetchFriendsList()
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    manualLoading.value = false
  }
}

const handleChangePassword = async () => {
  if (passwordLoading.value) return
  if (!passwordForm.value.old_password) {
    ElMessage.warning('请输入原密码')
    return
  }
  if (!passwordForm.value.new_password) {
    ElMessage.warning('请输入新密码')
    return
  }
  if (passwordForm.value.old_password === passwordForm.value.new_password) {
    ElMessage.warning('新密码不能与原密码相同')
    return
  }
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  passwordLoading.value = true
  try {
    const res = await changePassword(passwordForm.value.old_password, passwordForm.value.new_password)
    if (res.code === 200) {
      ElMessage.success('密码修改成功')
      passwordDialogVisible.value = false
      passwordForm.value.old_password = ''
      passwordForm.value.new_password = ''
      passwordForm.value.confirm_password = ''
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    passwordLoading.value = false
  }
}

const copyToClipboard = async (text) => {
  // 优先使用异步剪贴板 API（现代浏览器需安全上下文）；失败时回退到 execCommand
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 落到下方回退
  }
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    document.body.appendChild(textArea)
    textArea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textArea)
    return ok
  } catch {
    return false
  }
}

const handleGetCookie = async () => {
  if (cookieLoading.value) return
  if (!cookieForm.value.password) {
    ElMessage.warning('请输入密码')
    return
  }
  cookieLoading.value = true
  try {
    const res = await getCooker(cookieForm.value.password)
    if (res.code == 200) {
      const ok = await copyToClipboard(res.data.cooke)
      if (ok) {
        ElMessage.success('Cookie已复制到剪贴板')
        cookieDialogVisible.value = false
        cookieForm.value.password = ''
      } else {
        ElMessage.error('复制失败，请手动复制控制台输出的Cookie')
      }
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    cookieLoading.value = false
  }
}

const handleDieLogin = async () => {
  try {
    await dieLogin()
    setLoginStatus(false)
    localStorage.removeItem('douyin_token')
    ElMessage.success('已强制退出登录')
  } catch (error) {
    // 错误已由响应拦截器统一提示
  }
}

const handleSendCode = async () => {
  if (codeLoading.value) return
  if (!phoneForm.value.phone) {
    ElMessage.warning('请输入手机号')
    return
  }
  codeLoading.value = true
  try {
    const res = await sendVerifyCode(phoneForm.value.areacode, phoneForm.value.phone)
    if (res.code == 200) {
      ElMessage.success('验证码发送成功')
      codeCountdown.value = 60
      if (codeTimer) clearInterval(codeTimer)  // 避免重复计时器叠加
      codeTimer = setInterval(() => {
        codeCountdown.value--
        if (codeCountdown.value <= 0) {
          clearInterval(codeTimer)
          codeTimer = null
        }
      }, 1000)
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    codeLoading.value = false
  }
}

const handlePhoneLogin = async () => {
  if (phoneLoading.value) return
  if (!phoneForm.value.phone) {
    ElMessage.warning('请输入手机号')
    return
  }
  if (!phoneForm.value.code) {
    ElMessage.warning('请输入验证码')
    return
  }
  phoneLoading.value = true
  try {
    const res = await submitVerifyCode(phoneForm.value.code)
    if (res.code == 200) {
      ElMessage.success('登录成功')
      phoneDialogVisible.value = false
      setLoginStatus(true)
      username.value = ''
      await fetchUsername()
      // 与其他登录方式保持一致：登录成功后刷新好友列表
      await fetchFriendsList()
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    phoneLoading.value = false
  }
}

const handleGetScreenshot = async () => {
  if (screenshotLoading.value) return
  screenshotLoading.value = true
  screenshotUrl.value = ''
  try {
    const res = await getScrlk()
    if (res.code == 200) {
      screenshotUrl.value = 'data:image/png;base64,' + res.data
      screenshotPreviewVisible.value = true
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    screenshotLoading.value = false
  }
}

const handleForceLogin = async () => {
  try {
    await ElMessageBox.confirm('此操作会强制将服务端登录状态置为「已登录」，仅用于调试，是否继续？', '强制登录状态', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res = await forceLogin()
    if (res.code == 200) {
      ElMessage.success(res.data || '强制登录状态成功')
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
  }
}

const handleLogin = async () => {
  loginLoading.value = true
  loading.value = true
  qrcodeUrl.value = ''
  qrDialogVisible.value = true

  try {
    // 先初始化浏览器
    await initBrowser()
    // 获取二维码
    const res = await getLoginPng()
    if (res.data) {
      qrcodeUrl.value = res.data
      ElMessage.success('请使用抖音App扫码登录')
    } else {
      ElMessage.error('获取二维码失败')
      qrDialogVisible.value = false
    }
  } catch (error) {
    // 错误已由响应拦截器统一提示
    qrDialogVisible.value = false
  } finally {
    loginLoading.value = false
    loading.value = false
  }
}

onMounted(async () => {
  // 首次加载
  if (!settingsLoaded.value) {
    await checkLoginStatus()
    await fetchLastLoginIP()
    localStorage.setItem('douyin_settings_loaded', '1')
  }
})

// 组件卸载时清理验证码倒计时定时器，避免内存泄漏
onUnmounted(() => {
  if (codeTimer) {
    clearInterval(codeTimer)
    codeTimer = null
  }
})
</script>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
}

.stack-card {
  margin-top: 18px;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-1);
}

.account-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-label {
  font-size: 13px;
  color: var(--text-3);
}

.section-divider {
  height: 1px;
  background: var(--border);
  margin: 18px 0;
}

.login-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.config-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.gh-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}

.star-hint {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}

.config-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.config-label {
  color: var(--text-3);
  font-size: 13px;
}

.config-value {
  color: var(--text-1);
  font-size: 14px;
  font-weight: 500;
}

.phone-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.qrcode-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 280px;
}

.qrcode-wrapper {
  text-align: center;
}

.qrcode-img {
  width: 240px;
  height: 240px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.qrcode-hint {
  margin-top: 14px;
  color: var(--text-2);
  font-size: 14px;
}

.qrcode-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 15px;
  border-top: 1px solid var(--border);
}

/* 检测登录状态 · 二次确认弹窗 */
.check-tip {
  font-size: 14px;
  color: var(--text-1);
  line-height: 1.7;
}
.check-tip p {
  margin: 0 0 8px;
}
.check-tip-sub {
  font-size: 13px;
  color: var(--text-2);
}
.vnc-dialog-link {
  color: var(--info);
  word-break: break-all;
}
.vnc-dialog-link:hover {
  text-decoration: underline;
}

.state-wrapper {
  text-align: center;
  color: var(--text-3);
}

.state-wrapper .el-icon {
  font-size: 44px;
  margin-bottom: 10px;
}

.screenshot-img {
  max-width: 100%;
  max-height: 70vh;
  width: auto;
  height: auto;
  display: block;
  margin: 0 auto;
  border-radius: var(--radius-md);
}
</style>
