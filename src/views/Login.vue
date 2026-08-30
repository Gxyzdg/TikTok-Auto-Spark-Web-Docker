<template>
  <div class="login-container">
    <div class="login-bg">
      <div class="blob blob-1"></div>
      <div class="blob blob-2"></div>
      <div class="blob blob-3"></div>
    </div>

    <div class="login-card">
      <div class="login-brand">
        <div class="brand-logo"><FlameIcon /></div>
        <h1 class="brand-title">抖音火花助手</h1>
        <p class="brand-sub">抖音好友火花自动续期 · 管理后台</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          :loading="loading"
          class="login-button"
          @click="handleLogin"
        >
          {{ loading ? '登录中…' : '登 录' }}
        </el-button>
      </el-form>

      <p class="login-footer">仅供内网学习使用</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import FlameIcon from '../components/FlameIcon.vue'

const router = useRouter()
const userStore = useUserStore()

const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (loading.value) return
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        const result = await userStore.login(loginForm.username, loginForm.password)
        if (result.success) {
          ElMessage.success(result.message)
          router.push('/')
        } else {
          ElMessage.error(result.message)
        }
      } catch (error) {
        ElMessage.error('登录失败')
      } finally {
        loading.value = false
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
  background: linear-gradient(140deg, #ff9a4d 0%, #ff5a2f 48%, #d92d5a 100%);
}

.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.blob {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  filter: blur(2px);
}

.blob-1 {
  width: 420px;
  height: 420px;
  top: -120px;
  right: -80px;
  animation: floatY 7s ease-in-out infinite;
}

.blob-2 {
  width: 300px;
  height: 300px;
  bottom: -100px;
  left: -60px;
  background: rgba(255, 255, 255, 0.08);
  animation: floatY 9s ease-in-out infinite reverse;
}

.blob-3 {
  width: 180px;
  height: 180px;
  top: 18%;
  left: 12%;
  background: rgba(255, 255, 255, 0.1);
  animation: floatY 8s ease-in-out infinite;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 42px 36px 28px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 24px 60px rgba(120, 20, 30, 0.28);
  animation: fadeInUp 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.login-brand {
  text-align: center;
  margin-bottom: 30px;
}

.brand-logo {
  width: 60px;
  height: 60px;
  margin: 0 auto 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  color: #fff;
  border-radius: 16px;
  background: linear-gradient(135deg, #ff8a3d 0%, #ff4d5e 100%);
  box-shadow: 0 10px 22px rgba(255, 90, 47, 0.35);
  animation: floatY 3.5s ease-in-out infinite;
}

.brand-title {
  font-size: 22px;
  font-weight: 700;
  color: #1a1d24;
  letter-spacing: -0.01em;
}

.brand-sub {
  margin-top: 6px;
  font-size: 13px;
  color: #9aa1ad;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  background: #f6f7f9;
  box-shadow: none;
  padding: 4px 14px;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: 0 0 0 1px var(--primary) inset;
}

.login-form :deep(.el-input__inner) {
  font-size: 15px;
  color: #1a1d24;
}

.login-button {
  width: 100%;
  height: 46px;
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #ff8a3d 0%, #ff4d5e 100%);
  box-shadow: 0 10px 22px rgba(255, 90, 47, 0.32);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.login-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(255, 90, 47, 0.4);
}

.login-button:active {
  transform: translateY(0);
}

.login-footer {
  margin-top: 22px;
  text-align: center;
  font-size: 12px;
  color: #c0c5cd;
}

@media (max-width: 480px) {
  .login-card {
    padding: 34px 26px 24px;
  }
}
</style>
